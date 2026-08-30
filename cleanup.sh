#!/bin/bash
# cleanup any leftover probe-proxy containers/networks after a killed run
sg docker -c 'docker ps -a --filter label=probe-proxy -q | xargs -r docker rm -f'
sg docker -c 'docker network ls --filter name=probe-proxy -q | xargs -r docker network rm'
echo CLEANED
