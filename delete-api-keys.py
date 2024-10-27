import json
from datetime import datetime, timedelta

# third-party library
import oci

# Load input values
with open("configs/delete-api-key-config.json") as f:
    input_data = json.load(f)

tenancy_id = input_data["tenancy_id"]
delete_threshold_days = int(input_data["api_key_delete_threshold_days"])
users_to_exclude = input_data["users_to_exclude"]
dry_run = input_data["dry_run"]

# Calculate threshold date
threshold_timestamp = datetime.now().timestamp() - delete_threshold_days * 24 * 60 * 60


# Initialize OCI Identity Client
config = oci.config.from_file()
identity = oci.identity.IdentityClient(config)


# https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/api/identity/client/oci.identity.IdentityClient.html#oci.identity.IdentityClient.list_domains
def get_domains(compartment_id):
    domains = {}
    for domain in identity.list_domains(compartment_id=compartment_id).data:
        domains[domain.display_name] = {"id": domain.id, "url": domain.url}
    return domains


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.list_users
def get_users(identity_domain_client, domain_url):
    users = identity_domain_client.list_users(count=500).data.resources
    user_details = {}
    for user in users:
        user_details[user.user_name] = user.ocid
    return user_details


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.list_api_keys
def get_api_keys(identity_domain_client, user_ocid):
    user_filter = f'user.ocid eq "{user_ocid}"'
    api_keys = identity_domain_client.list_api_keys(
        filter=user_filter, count=500
    ).data.resources

    api_key_details = {}
    for key in api_keys:
        api_key_details[key.id] = {
            "fingerprint": key.fingerprint,
            "ocid": key.ocid,
            "created_at": datetime.fromisoformat(key.meta.created),
        }
    return api_key_details


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.delete_api_key
def delete_api_key(identity_domain_client, delete_api_key_ocid):
    identity_domain_client.delete_api_key(api_key_id=delete_api_key_ocid)


# Get all users along with their api keys in each domain in the compartment
def get_users_with_api_keys_in_domain(identity_domain_client, domain_url):
    users = get_users(identity_domain_client, domain_url)
    users_with_api_keys = {}
    for user in users:
        user_ocid = users[user]
        users_with_api_keys[user] = get_api_keys(identity_domain_client, user_ocid)
    return users_with_api_keys


# specify if an API key should be deleted
def should_delete_api_key(api_key_details):
    return (
        api_key_details["created_at"].timestamp() < threshold_timestamp
        and len(api_key_details) > 0
    )


# Get users with API keys to delete
def get_users_with_api_keys_to_delete(users_with_api_keys):
    users_with_api_keys_to_delete = {}
    for user in users_with_api_keys:
        if user in users_to_exclude:
            print("Excluding user :", user)
            continue
        api_keys = users_with_api_keys[user]
        users_with_api_keys_to_delete[user] = {}
        for api_key_id in api_keys:
            if should_delete_api_key(api_keys[api_key_id]):
                users_with_api_keys_to_delete[user][api_key_id] = api_keys[api_key_id]
    return users_with_api_keys_to_delete


# delete api keys for all users in a domain
def delete_api_keys_for_domain(identity_domain_client, users_with_api_keys_to_delete):
    for user in users_with_api_keys_to_delete:
        for api_key_id in users_with_api_keys_to_delete[user]:
            print(f"Deleting API keys for user: {user} with api key id: {api_key_id}")
            is_deleted = delete_api_key(
                identity_domain_client,
                api_key_id,
            )
            if is_deleted is None:
                print(f"API key {api_key_id} deleted successfully")


if __name__ == "__main__":

    users_with_api_keys_to_delete = {}
    compartments = {"root": tenancy_id}

    # for root compartment, get all domains
    for compartment_name in compartments:
        compartment_id = compartments[compartment_name]
        domains = get_domains(compartment_id=compartment_id)

        # Get all users in each domain in the root compartment
        for domain in domains:
            domain_url = domains[domain]["url"]
            identity_domain_client = oci.identity_domains.IdentityDomainsClient(
                config, service_endpoint=domain_url
            )

            users_with_api_keys = get_users_with_api_keys_in_domain(
                identity_domain_client, domain_url
            )

            users_with_api_keys_to_delete[domain_url] = (
                get_users_with_api_keys_to_delete(users_with_api_keys)
            )

    print("Users with API keys to delete:")
    print(
        json.dumps(list(users_with_api_keys_to_delete.values()), indent=4, default=str)
    )

    if not dry_run:
        print("Deleting API keys...")
        for domain_url in users_with_api_keys_to_delete:
            identity_domain_client = oci.identity_domains.IdentityDomainsClient(
                config, service_endpoint=domain_url
            )
            delete_api_keys_for_domain(
                identity_domain_client, users_with_api_keys_to_delete[domain_url]
            )
    else:
        print("Dry run enabled. No API keys will be deleted.")
