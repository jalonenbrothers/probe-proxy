// tlsprobe: pinned TLS negotiation probe (IDEA-11 pq-gate, builder M0).
// Built statically (CGO_ENABLED=0) inside a golang:1.24-alpine container so
// it NEVER uses host OpenSSL — critic binding condition (b): host OpenSSL
// 3.0 is classical-only and must never silently under-report PQ.
//
// Emits a JSON negotiation fingerprint of what the image's TLS endpoint
// ACTUALLY negotiates with a modern PQ-capable client: TLS versions
// accepted, kex groups accepted (enumerated via forced single-group
// handshakes — PQ hybrids included), negotiated cipher suite, cert sig
// alg / key type / bits, ALPN. Any error -> exit 1 with {"error": ...}:
// FAIL-CLOSED (the gate treats probe error as HOLD, never ALLOW).
//
// Honesty note: Go crypto/tls does not expose the negotiated TLS 1.3 group
// client-side, so the kex surface is captured as `groups_accepted` — the
// set of groups with which a complete handshake succeeds when the client
// offers ONLY that group. That is the negotiation surface a PQ-capable
// client population actually encounters; a PQ-hybrid group appearing or
// disappearing from this set is exactly the event the gate exists to
// catch. Preference ORDER is not captured (documented limitation).
//
// Usage: tlsprobe <host:port> [sni]
package main

import (
	"crypto/ecdsa"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

const PROBE_ID = "tlsprobe-go-static-v1 (Go crypto/tls, PQ-hybrid-capable client)"

func fail(msg string) {
	out, _ := json.Marshal(map[string]any{"error": msg})
	fmt.Println(string(out))
	os.Exit(1)
}

// groups the probe enumerates via forced single-group handshakes;
// PQ hybrids (ML-KEM standardized + Kyber draft) + classical curves
// (Kyber draft groups were removed from Go 1.24 crypto/tls — only the
// standardized ML-KEM hybrid remains; recorded honestly in RUN.md)
var PROBE_GROUPS = []tls.CurveID{
	tls.X25519MLKEM768,
	tls.X25519, tls.CurveP256, tls.CurveP384, tls.CurveP521,
}

func groupString(g tls.CurveID) string {
	switch g {
	case tls.X25519MLKEM768:
		return "X25519MLKEM768"
	case tls.X25519:
		return "X25519"
	case tls.CurveP256:
		return "P-256"
	case tls.CurveP384:
		return "P-384"
	case tls.CurveP521:
		return "P-521"
	}
	return fmt.Sprintf("unknown(%d)", g)
}

// fullHandshake: modern full-featured client (all groups incl. PQ hybrids
// offered; server picks by its own preference). Returns negotiated state.
func fullHandshake(addr, sni string) (*tls.ConnectionState, error) {
	conf := &tls.Config{
		ServerName:         sni,
		InsecureSkipVerify: true, // fingerprinting, not validation
		MinVersion:         tls.VersionTLS10,
	}
	conn, err := tls.Dial("tcp", addr, conf)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	cs := conn.ConnectionState()
	return &cs, nil
}

// groupsAccepted: forced single-group handshakes — the set of groups the
// server will negotiate with (TLS1.2 curve or TLS1.3 key_share).
func groupsAccepted(addr, sni string) []string {
	var accepted []string
	for _, g := range PROBE_GROUPS {
		conf := &tls.Config{
			ServerName:         sni,
			InsecureSkipVerify: true,
			MinVersion:         tls.VersionTLS12,
			MaxVersion:         tls.VersionTLS13,
			CurvePreferences:   []tls.CurveID{g},
		}
		conn, err := tls.Dial("tcp", addr, conf)
		if err == nil {
			accepted = append(accepted, groupString(g))
			conn.Close()
		}
	}
	sort.Strings(accepted)
	return accepted
}

// tlsVersionsAccepted: forced single-version handshakes, descending.
func tlsVersionsAccepted(addr, sni string) []string {
	type ver struct{ min, max uint16; n string }
	versions := []ver{
		{tls.VersionTLS13, tls.VersionTLS13, "TLS1.3"},
		{tls.VersionTLS12, tls.VersionTLS12, "TLS1.2"},
		{tls.VersionTLS11, tls.VersionTLS11, "TLS1.1"},
		{tls.VersionTLS10, tls.VersionTLS10, "TLS1.0"},
	}
	var accepted []string
	for _, v := range versions {
		conf := &tls.Config{
			ServerName:         sni,
			InsecureSkipVerify: true,
			MinVersion:         v.min,
			MaxVersion:         v.max,
		}
		conn, err := tls.Dial("tcp", addr, conf)
		if err == nil {
			accepted = append(accepted, v.n)
			conn.Close()
		}
	}
	return accepted
}

func versionString(v uint16) string {
	switch v {
	case tls.VersionTLS13:
		return "TLS1.3"
	case tls.VersionTLS12:
		return "TLS1.2"
	case tls.VersionTLS11:
		return "TLS1.1"
	case tls.VersionTLS10:
		return "TLS1.0"
	}
	return fmt.Sprintf("0x%04x", v)
}

func main() {
	if len(os.Args) < 2 {
		fail("usage: tlsprobe host:port [sni]")
	}
	addr := os.Args[1]
	sni := ""
	if len(os.Args) > 2 {
		sni = os.Args[2]
	} else {
		sni = strings.Split(addr, ":")[0]
	}

	cs, err := fullHandshake(addr, sni)
	if err != nil {
		fail("dial: " + err.Error())
	}

	certCN, certIssuer, certSigAlg, certKeyType := "none", "", "", ""
	certKeyBits := 0
	if len(cs.PeerCertificates) > 0 {
		c := cs.PeerCertificates[0]
		certCN = c.Subject.CommonName
		certIssuer = c.Issuer.CommonName
		certSigAlg = c.SignatureAlgorithm.String()
		switch pk := c.PublicKeyAlgorithm; pk {
		case x509.RSA:
			certKeyType = "RSA"
			if k, ok := c.PublicKey.(*rsa.PublicKey); ok {
				certKeyBits = k.N.BitLen()
			}
		case x509.ECDSA:
			certKeyType = "ECDSA"
			if k, ok := c.PublicKey.(*ecdsa.PublicKey); ok {
				certKeyBits = k.Curve.Params().BitSize
			}
		case x509.Ed25519:
			certKeyType = "Ed25519"
			certKeyBits = 256
		default:
			certKeyType = pk.String()
		}
	}

	out := map[string]any{
		"probe_client":   PROBE_ID,
		"tls_version":    versionString(cs.Version),
		"tls_versions":   tlsVersionsAccepted(addr, sni),
		"groups_accepted": groupsAccepted(addr, sni),
		"cipher_suite":   tls.CipherSuiteName(cs.CipherSuite),
		"alpn":           cs.NegotiatedProtocol,
		"cert_cn":        certCN,
		"cert_issuer_cn": certIssuer,
		"cert_sig_alg":   certSigAlg,
		"cert_key_type":  certKeyType,
		"cert_key_bits":  certKeyBits,
		"resumption":     cs.DidResume,
		"ocsp_stapled":   len(cs.OCSPResponse) > 0,
		"sct_count":      len(cs.SignedCertificateTimestamps),
	}
	b, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		fail("marshal: " + err.Error())
	}
	fmt.Println(string(b))
}
