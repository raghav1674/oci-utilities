#!/usr/bin/env bash

read -p "Enter the client_id: " client_id
read -p "Enter the client_secret: " client_secret
read -p "Enter the domain_url: " domain_url
read -p "Enter the expiry_time in seconds: (defaults to 1 year) " expiry_time


# Check if the required inputs are provided
if [ -z "$client_id" ] || [ -z "$client_secret" ] || [ -z "$domain_url" ]; then
    echo "Please provide all the required inputs"
    exit 1
fi

if [ -z "$expiry_time" ]; then
    expiry_time=31622400
fi


echo "Encoding the client_id and client_secret"

encoded_cred=$(echo -n "$client_id:$client_secret" | base64)


echo "Getting the access_token and saving it to access_token.txt"

access_token=$(curl -s -i \
    -H "Authorization: Basic $encoded_cred" \
    -H "Content-Type: application/x-www-form-urlencoded;charset=UTF-8" \
    --request POST $domain_url/oauth2/v1/token \
    -d "grant_type=client_credentials&scope=urn:opc:idm:__myscopes__%20urn:opc:resource:expiry=$expiry_time"  | awk -F"\"" '{print $4}')


echo $access_token > access_token.txt


echo "Testing the access_token"

status_code=$(curl -X GET \
   -H "Content-Type:application/scim+json" \
   -H "Authorization: Bearer $(cat access_token.txt)" \
   $domain_url/admin/v1/Users -s -w "%{http_code}\n" -o /dev/null)

if [ $status_code -eq 200 ]; then
    echo "Access token is valid"
else
    echo "Access token is invalid. Please check the client_id, client_secret and domain_url"
fi
