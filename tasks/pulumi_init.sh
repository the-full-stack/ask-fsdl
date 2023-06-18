#!/bin/bash


env=${1:-"dev"}

# check if the stack exists
if pulumi -C bot/ stack ls | grep -q "$env"; then
    echo "pulumi stack $env found"
else
    echo "pulumi stack $env does not exist. Creating..."
    pulumi -C stack init "$env"
fi
