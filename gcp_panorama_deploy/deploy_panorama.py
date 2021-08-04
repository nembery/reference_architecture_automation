import sys
# from datetime import datetime
import time
import os
import socket
import requests
import json
from pathlib import Path
# from requests.exceptions import ConnectionError
# from requests import get
from docker import DockerClient
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend

# This setting change removes the warnings when the script tries to connect to Panorama and check its availability
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Function to convert seconds to a Hours: Minutes: Seconds display
def convert(seconds):
    min, sec = divmod(seconds, 60)
    hour, min = divmod(min, 60)
    return '%d:%02d:%02d' % (hour, min, sec)


# Pull in the GCP Provider variables. These are set in the Skillet Environment and are hidden variables so the
# user doesn't need to adjust them everytime.
variables = dict(TF_IN_AUTOMATION='True')
variables.update(TF_VAR_deployment_name=os.environ.get('DEPLOYMENT_NAME'), TF_VAR_vpc_cidr_block=os.environ.get(
                'vpc_cidr_block'), TF_VAR_enable_ha=os.environ.get('enable_ha'), TF_VAR_folder=os.environ.get('FOLDER'),
                TF_VAR_billing_account=os.environ.get('BILLING_ACCOUNT'), TF_VAR_gcp_region=os.environ.get('GCP_REGION'))
# A variable the defines if we are creating or destroying the environment via terraform. Set in the dropdown
# on Panhandler.
tfcommand = (os.environ.get('Init'))

# Define the working directory for the container as the terraform directory and not the directory of the skillet.
path = Path(os.getcwd())
wdir = str(path.parents[0])+'/terraform/gcp/panorama/'

# If the variable is defined for the script to automatically determine the public IP, then capture the public IP
# and add it to the Terraform variables. If it isn't then add the IP address block the user defined and add it
# to the Terraform variables.
if (os.environ.get('specify_network')) == 'auto':
    # Using verify=false in case the container is behind a firewall doing decryption.
    ip = requests.get('https://api.ipify.org', verify=False).text+'/32'
    variables.update(TF_VAR_onprem_IPaddress=ip)
else:
    variables.update(TF_VAR_onprem_IPaddress=(os.environ.get('onprem_cidr_block')))

# The script uses a terraform docker container to run the terraform plan. The script uses the docker host that
# panhandler is running on to run the new conatiner. /var/lib/docker.sock must be mounted on panhandler
client = DockerClient()

if os.path.exists(wdir+'gcloud') is not True:
    print('Generating Gcloud Credential File')
    tempv = str(os.environ.get('GOOGLE_CREDENTIALS'))
    # Write the credentials to the filesystem so they can be used by Gcloud later.
    with open(wdir+'gcloud', 'w') as gcpfile:
        gcpfile.write(tempv)
    # Add the path to the credentials to the variables sent to Terraform.
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=wdir+'gcloud')
    # If the keys already exist don't recreate them or else you might not be able to access a resource you
    # previously created but havent set the password on.
else:
    print('GCP credential file exists already, skipping....')
    # Add the path to the credentials to the variables sent to Terraform.
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=wdir+'gcloud')

# If the variable is set to apply then create the environment and check for Panorama availabliity
if tfcommand == 'apply':
    # Generate a new RSA keypair to use to SSH to the VM. If you are using your own automation outside of
    # Panhandler then you should use your own keys.
    if os.path.exists(wdir+'id_rsa') is not True:
        print('Generating Crypto Key')
        key = rsa.generate_private_key(
            backend=crypto_default_backend(),
            public_exponent=65537,
            key_size=2048)
        private_key = key.private_bytes(
            crypto_serialization.Encoding.PEM,
            crypto_serialization.PrivateFormat.TraditionalOpenSSL,
            crypto_serialization.NoEncryption()).decode('utf-8')
        public_key = key.public_key().public_bytes(
            crypto_serialization.Encoding.OpenSSH,
            crypto_serialization.PublicFormat.OpenSSH).decode('utf-8')
        # Write the keys to the filesystem so they can be used by Ansible later to set a password.
        with open(wdir+'pub', 'w') as pubfile, open(wdir+'id_rsa', 'w') as privfile:
            privfile.write(private_key)
            pubfile.write(public_key)
        # Add the public key to the variables sent to Terraform so it can create the GCP key pair.
        variables.update(TF_VAR_ra_key=public_key)
    # If the keys already exist don't recreate them or else you might not be able to access a resource you
    # previously created but havent set the password on.
    else:
        print('Crypto Key exists already, skipping....')
        public_key = open(wdir+'pub', 'r')
        # Add the public key to the variables sent to Terraform so it can create the GCP key pair.
        variables.update(TF_VAR_ra_key=public_key.read())

    # Init terraform with the modules and providers. The continer will have the some volumes as Panhandler.
    # This allows it to access the files Panhandler downloaded from the GIT repo.
    container = client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform init -no-color -input=false', auto_remove=True,
                                      volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    # Run terraform apply
    container = client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform apply -auto-approve -no-color -input=false',
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    #  The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

    # Capture the IP addresses of Panorama using Terraform output
    eip = json.loads(client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform output -json -no-color', auto_remove=True,
                                           volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                           environment=variables).decode('utf-8'))
    try:
        panorama_ip = (eip['primary_eip']['value'])
    except Exception:
        print('Error: Unable to capture Panorama\'s IP address')
        sys.exit(1)

    # Inform the user of Panorama's external IP address
    print('')
    print('The Panorama IP address is '+panorama_ip)

    # Inform the user of the secondary Panorama's external IP address
    if os.environ.get('enable_ha') == 'true':
        secondary_ip = (eip['secondary_eip']['value'])
        print('The Secondary Panorama IP address is '+secondary_ip)

    # Panorama is deployed but it isn't ready to be configured until it is fully booted. Check for that state by trying
    # to reach the web page.
    print('')
    print('Checking if Panorama is fully booted. This can take 30 minutes or more...')

    temptime = 0

    while 1:
        try:
            request = requests.get(
                'https://'+panorama_ip, verify=False, timeout=5)
        except requests.ConnectionError:
            print('Panorama is still booting.... ['+convert(temptime)+'s elapsed]')
            time.sleep(5)
            temptime = temptime+10
            continue
        except requests.Timeout:
            print('Timeout Error')
            time.sleep(5)
            temptime = temptime+10
            continue
        except requests.RequestException as e:
            print("General Error - this normally isn't a problem as the script will keep retrying")
            print(str(e))
            continue
        else:
            print('Panorama is available')
            break
    # Once the primary Panorama is available, check the secondary Panorama if there is one.
    if os.environ.get('enable_ha') == 'true':
        while 1:
            try:
                request = requests.get(
                    'https://'+secondary_ip, verify=False, timeout=5)
            except requests.ConnectionError:
                print('The Secondary Panorama is still booting.... ['+convert(temptime)+'s elapsed]')
                time.sleep(5)
                temptime = temptime+10
                continue
            except requests.Timeout:
                print('Timeout Error')
                time.sleep(5)
                temptime = temptime+10
                continue
            except requests.RequestException as e:
                print("General Error - this normally isn't a problem as the script will keep retrying")
                print(str(e))
                continue
            else:
                print('The Secondary Panorama is available')
                break

# If the variable is destroy, then destroy the environment and remove the SSH keys.
elif tfcommand == 'destroy':
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=wdir+'gcloud')
    variables.update(TF_VAR_ra_key="")
    container = client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform destroy -auto-approve -no-color -input=false',
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    # Remove the SSH keys we used to provision Panorama from the container.
    print('Removing local keys....')
    try:
        os.remove(wdir+'pub')
    except Exception:
        print('  There where no public keys to remove')
    try:
        os.remove(wdir+'id_rsa')
    except Exception:
        print('  There where no private keys to remove')
    try:
        os.remove(wdir+'gcloud')
    except Exception:
        print('  There where no GCP credentials to remove')

sys.exit(0)
