#!/bin/bash
docker ps --filter "name=hiclaw" --format "table {{.Names}}\t{{.Status}}" 2>&1
