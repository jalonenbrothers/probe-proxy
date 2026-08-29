# probe-proxy Milestone 0 — Probe-Coverage Matrix

Apps probed: 10 (+ httpbin sanity target). Result: **10/10 distinguishable — DISTINGUISHABLE (>=8/10)**

## Distinguishability verdict

| app | distinguishable |
|---|---|
| immich | YES |
| jellyfin | YES |
| nextcloud | YES |
| homeassistant | YES |
| pihole | YES |
| gitea | YES |
| grafana | YES |
| uptimekuma | YES |
| n8n | YES |
| vaultwarden | YES |

## Probe discriminative power (distinct value-classes across apps)

| probe | classes |
|---|---|
| root | 9 |
| common_paths | 8 |
| large_post | 8 |
| method_allow | 8 |
| well_known | 6 |
| xfp_upgrade | 6 |
| sse | 5 |
| tls_redirect | 4 |
| compression | 3 |
| header_reflect | 2 |
| redirect_chain | 2 |
| websocket | 2 |

## Fingerprint grid (key value per probe x app)

| probe | immich | jellyfin | nextcloud | homeassistant | pihole | gitea | grafana | uptimekuma | n8n | vaultwarden |
|---|---|---|---|---|---|---|---|---|---|---|
| common_paths | {"path_statuses": "{\"/admin\": 200, \"/api\": 404, \"/api/h | {"path_statuses": "{\"/admin\": 503, \"/api\": 503, \"/api/h | {"path_statuses": "{\"/admin\": 404, \"/api\": 404, \"/api/h | {"path_statuses": "{\"/admin\": 404, \"/api\": 404, \"/api/h | {"path_statuses": "{\"/admin\": 308, \"/api\": 404, \"/api/h | {"path_statuses": "{\"/admin\": 404, \"/api\": 404, \"/api/h | {"path_statuses": "{\"/admin\": 302, \"/api\": 401, \"/api/h | {"path_statuses": "{\"/admin\": 200, \"/api\": 200, \"/api/h | {"path_statuses": "{\"/admin\": 200, \"/api\": 200, \"/api/h | {"path_statuses": "{\"/admin\": 200, \"/api\": 404, \"/api/h |
| compression | {"compression": "none", "vary": false} | {"compression": "br", "vary": true} | {"compression": "gzip", "vary": true} | {"compression": "br", "vary": true} | {"compression": "none", "vary": false} | {"compression": "none", "vary": false} | {"compression": "gzip", "vary": true} | {"compression": "none", "vary": false} | {"compression": "none", "vary": false} | {"compression": "none", "vary": false} |
| header_reflect | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": true, "xff_ackno | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn | {"cookie_secure_flag": false, "set_cookie": false, "xff_ackn |
| large_post | {"post10mb_len_header": "27", "post10mb_status": 404} | {"post10mb_len_header": "", "post10mb_status": 200} | {"post10mb_len_header": "1665", "post10mb_status": 200} | {"post10mb_len_header": "23", "post10mb_status": 405} | {"post10mb_len_header": "", "post10mb_status": 405} | {"post10mb_len_header": "", "post10mb_status": 200} | {"post10mb_len_header": "", "post10mb_status": 200} | {"post10mb_len_header": "140", "post10mb_status": 404} | {"post10mb_len_header": "31", "post10mb_status": 200} | {"post10mb_len_header": "1834", "post10mb_status": 404} |
| method_allow | {"options_allow": "", "propfind_status": 404} | {"options_allow": "", "propfind_status": 302} | {"options_allow": "", "propfind_status": 200} | {"options_allow": "GET", "propfind_status": 405} | {"options_allow": "GET, POST, PUT, DELETE, HEAD, OPTIONS, CO | {"options_allow": "GET, POST", "propfind_status": 405} | {"options_allow": "", "propfind_status": 302} | ERROR | {"options_allow": "", "propfind_status": 200} | {"options_allow": "", "propfind_status": 400} |
| redirect_chain | {"redirect_chain": "none", "redirect_hops": 0} | {"redirect_chain": "302>200", "redirect_hops": 1} | {"redirect_chain": "none", "redirect_hops": 0} | {"redirect_chain": "302>200", "redirect_hops": 1} | {"redirect_chain": "none", "redirect_hops": 0} | {"redirect_chain": "none", "redirect_hops": 0} | {"redirect_chain": "302>200", "redirect_hops": 1} | {"redirect_chain": "302>200", "redirect_hops": 1} | {"redirect_chain": "none", "redirect_hops": 0} | {"redirect_chain": "none", "redirect_hops": 0} |
| root | {"root_location": "", "root_powered_by": "Express", "root_se | {"root_location": "web/", "root_powered_by": "", "root_serve | {"root_location": "", "root_powered_by": "PHP/8.5.9", "root_ | {"root_location": "/onboarding.html", "root_powered_by": "", | {"root_location": "", "root_powered_by": "", "root_server":  | {"root_location": "", "root_powered_by": "", "root_server":  | {"root_location": "/login", "root_powered_by": "", "root_ser | {"root_location": "/dashboard", "root_powered_by": "", "root | {"root_location": "", "root_powered_by": "", "root_server":  | {"root_location": "", "root_powered_by": "", "root_server":  |
| sse | {"sse_chunks_observed": 1, "sse_content_type": "application/ | {"sse_chunks_observed": 2, "sse_content_type": "text/html",  | {"sse_chunks_observed": 1, "sse_content_type": "text/html",  | {"sse_chunks_observed": 1, "sse_content_type": "text/html",  | {"sse_chunks_observed": 5, "sse_content_type": "text/html",  | {"sse_chunks_observed": 5, "sse_content_type": "text/html",  | {"sse_chunks_observed": 3, "sse_content_type": "text/html",  | {"sse_chunks_observed": 1, "sse_content_type": "text/html",  | {"sse_chunks_observed": 1, "sse_content_type": "text/html",  | {"sse_chunks_observed": 1, "sse_content_type": "text/html",  |
| tls_redirect | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": true, "tls_redirect_status": 3 | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  | {"tls_redirect_honors_param": false, "tls_redirect_status":  |
| websocket | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": ["/socket.io/?EIO=4& | {"ws_any_data": false, "ws_open_paths": "none"} | {"ws_any_data": false, "ws_open_paths": "none"} |
| well_known | {"well_known": "{\"acme-challenge/test\": 200, \"caldav\": 2 | {"well_known": "{\"acme-challenge/test\": 503, \"caldav\": 5 | {"well_known": "{\"acme-challenge/test\": 404, \"caldav\": 3 | {"well_known": "{\"acme-challenge/test\": 404, \"caldav\": 4 | {"well_known": "{\"acme-challenge/test\": 404, \"caldav\": 4 | {"well_known": "{\"acme-challenge/test\": 404, \"caldav\": 4 | {"well_known": "{\"acme-challenge/test\": 302, \"caldav\": 3 | {"well_known": "{\"acme-challenge/test\": 200, \"caldav\": 2 | {"well_known": "{\"acme-challenge/test\": 200, \"caldav\": 2 | {"well_known": "{\"acme-challenge/test\": 422, \"caldav\": 4 |
| xfp_upgrade | {"xfp_location": "", "xfp_status": 200} | {"xfp_location": "web/", "xfp_status": 302} | {"xfp_location": "", "xfp_status": 200} | {"xfp_location": "/onboarding.html", "xfp_status": 302} | {"xfp_location": "", "xfp_status": 403} | {"xfp_location": "", "xfp_status": 200} | {"xfp_location": "/login", "xfp_status": 302} | {"xfp_location": "/dashboard", "xfp_status": 302} | {"xfp_location": "", "xfp_status": 200} | {"xfp_location": "", "xfp_status": 200} |
