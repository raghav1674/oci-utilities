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
domains_to_consider = input_data["domains"]
dry_run = input_data["dry_run"]

# Calculate threshold date
threshold_timestamp = datetime.now().timestamp() - delete_threshold_days * 24 * 60 * 60


# Initialize OCI Identity Client
config = oci.config.from_file()
identity = oci.identity.IdentityClient(config)


def _paginate_call(method_name, **kwargs):
    """
    Paginate the list calls to OCI API
    params:
        method_name: the name of the method to call (return type should be {'resources': [], 'next_page': str, 'has_next_page': bool})
        kwargs: the arguments to pass to the method
    """
    response = globals()["%s" % method_name](**kwargs)
    resources = response["resources"]

    while response["has_next_page"]:
        response = globals()["%s" % method_name](**kwargs, page=response["next_page"])
        resources += response.data.resources

    return resources


# https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/api/identity/client/oci.identity.IdentityClient.html#oci.identity.IdentityClient.list_domains
def get_domains(compartment_id):
    """
    Get all domains in a compartment
    params:
        compartment_id: the compartment id (root compartment id is tenancy_id)
    """
    domains = {}
    for domain in identity.list_domains(compartment_id=compartment_id).data:
        domains[domain.display_name] = {"id": domain.id, "url": domain.url}
    return domains


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.list_users
def get_users(identity_domain_client, limit=500, page=None):
    """
    Get all users in a domain
    params:
        identity_domain_client: the identity domain client
        limit: the number of users to fetch in each page
        page: the page token to fetch the next page
    """
    response = identity_domain_client.list_users(count=limit, page=page)
    users = response.data.resources
    user_details = {}
    for user in users:
        user_details[user.user_name] = user.ocid
    return {
        "resources": user_details,
        "next_page": response.next_page,
        "has_next_page": response.has_next_page,
    }


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.list_api_keys
def get_api_keys(identity_domain_client, user_ocid, limit=500, page=None):
    """
    Get all api keys for a user in a domain
    params:
        identity_domain_client: the identity domain client
        user_ocid: the user ocid
        limit: the number of api keys to fetch in each page
        page: the page token to fetch the next page
    """
    user_filter = f'user.ocid eq "{user_ocid}"'
    response = identity_domain_client.list_api_keys(
        filter=user_filter, count=limit, page=page
    )
    api_keys = response.data.resources
    api_key_details = {}
    for key in api_keys:
        api_key_details[key.id] = {
            "fingerprint": key.fingerprint,
            "ocid": key.ocid,
            "created_at": datetime.fromisoformat(key.meta.created),
        }
    return {
        "resources": api_key_details,
        "next_page": response.next_page,
        "has_next_page": response.has_next_page,
    }


# https://docs.oracle.com/en-us/iaas/tools/python/2.136.0/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html#oci.identity_domains.IdentityDomainsClient.delete_api_key
def delete_api_key(identity_domain_client, delete_api_key_ocid):
    """
    Delete an API key
    params:
        identity_domain_client: the identity domain client
        delete_api_key_ocid: the api key ocid
    """
    identity_domain_client.delete_api_key(api_key_id=delete_api_key_ocid)


# Get all users along with their api keys in each domain in the compartment
def get_users_with_api_keys_in_domain(identity_domain_client):
    """
    Get all users along with their api keys in a domain
    params:
        identity_domain_client: the identity
    """
    users = _paginate_call(
        "get_users",
        identity_domain_client=identity_domain_client,
        limit=500,
    )
    users_with_api_keys = {}
    for user in users:
        user_ocid = users[user]
        users_with_api_keys[user] = _paginate_call(
            "get_api_keys",
            identity_domain_client=identity_domain_client,
            user_ocid=user_ocid,
            limit=500,
        )
    return users_with_api_keys


# specify if an API key should be deleted
def should_delete_api_key(api_key_details):
    """
    Specify if an API key should be deleted
    params:
        api_key_details: the details of the api key
    """
    return api_key_details["created_at"].timestamp() < threshold_timestamp


# Get users with API keys to delete
def get_users_with_api_keys_to_delete(users_with_api_keys):
    """
    Get users with API keys to delete
    params:
        users_with_api_keys: the users along with their api keys
    """
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

    # filter out the users with no api keys
    users_with_api_keys_to_delete = {
        user: users_with_api_keys_to_delete[user]
        for user in users_with_api_keys_to_delete
        if len(users_with_api_keys_to_delete[user]) > 0
    }
    return users_with_api_keys_to_delete


# delete api keys for all users in a domain
def delete_api_keys_for_domain(identity_domain_client, users_with_api_keys_to_delete):
    """
    Delete API keys for all users in a domain
    params:
        identity_domain_client: the identity domain client
        users_with_api_keys_to_delete: the users along with their api keys to delete
    """
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
            if len(domains_to_consider) > 0 and (
                domains[domain]["id"] not in domains_to_consider
            ):
                print(f"Excluding domain: {domain}")
                continue
            domain_url = domains[domain]["url"]
            identity_domain_client = oci.identity_domains.IdentityDomainsClient(
                config, service_endpoint=domain_url
            )

            users_with_api_keys = get_users_with_api_keys_in_domain(
                identity_domain_client
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
