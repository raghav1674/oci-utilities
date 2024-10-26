## OCI Utility

Repository where the OCI(Oracle Cloud Infrastructure) related scripts or utilities are maintained by me for my usecases.

#### Prerequisites:

1. Follow the steps as mentioned in the [OCI Document](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm) to configure the oci config file
2. Make sure python3 is installed and [virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/) for python is setup.

##### Steps to run the scripts available in this repo:

1. Clone the repository
2. `cd oracle-utilities`
3. Activate the virtualenv, depending upon the os as mentioned in the Step 2 of Prerequisites
4. Install dependenices.
   `python -m pip install -r requirements.txt` or `python3 -m pip3 install -r requirements.txt`
5. Update the config.json as per the requirement
6. Run the script.
   `python delete-api-keys.py` or `python3 delete-api-keys.py`
