#!/bin/sh
# nextcloud TLS wrapper: enable Apache SSL + our fixed probe cert.
# The nextcloud image ships default-ssl.conf with snakeoil paths.
sed -i 's#/etc/ssl/certs/ssl-cert-snakeoil.pem#/ssl/cert.pem#; s#/etc/ssl/private/ssl-cert-snakeoil.key#/ssl/key.pem#' /etc/apache2/sites-available/default-ssl.conf
a2enmod ssl >/dev/null 2>&1
a2ensite default-ssl >/dev/null 2>&1
exec apache2-foreground
