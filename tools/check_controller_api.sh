#!/bin/bash
docker exec hiclaw-controller sh -c "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && curl -sv http://127.0.0.1:8090/api/workers 2>&1" | head -30
