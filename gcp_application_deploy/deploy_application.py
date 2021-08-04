import sys
# from datetime import datetime
# import time
import os
import socket
from pathlib import Path
# from requests.exceptions import ConnectionError
# from requests import get
from docker import DockerClient
from jinja2 import Environment, FileSystemLoader

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
variables.update(TF_VAR_deployment_name=os.environ.get('DEPLOYMENT_NAME'), TF_VAR_enable_ha=os.environ.get('enable_ha'),
                 TF_VAR_folder=os.environ.get('FOLDER'), TF_VAR_billing_account=os.environ.get('BILLING_ACCOUNT'),
                 TF_VAR_gcp_region=os.environ.get('GCP_REGION'), TF_VAR_authcode=os.environ.get('authcode'),
                 PANOS_PASSWORD=os.environ.get('PASSWORD'), PANOS_USERNAME='admin')
# A variable the defines if we are creating or destroying the environment via terraform. Set in the dropdown
# on Panhandler.
tfcommand = (os.environ.get('Init'))

# Define the working directory for the container as the terraform directory and not the directory of the skillet.
path = Path(os.getcwd())
shared_wdir = str(path.parents[0])+'/terraform/gcp/shared-vpc-deploy/'
wdir = str(path.parents[0])+'/terraform/gcp/shared-vpc-application/'

# The script uses a terraform docker container to run the terraform plan. The script uses the docker host that
# panhandler is running on to run the new conatiner. /var/lib/docker.sock must be mounted on panhandler
client = DockerClient()

if os.path.exists(shared_wdir+'gcloud') is not True:
    print('Generating Gcloud Credential File')
    tempv = str(os.environ.get('GOOGLE_CREDENTIALS'))
    # Write the credentials to the filesystem so they can be used by Gcloud later.
    with open(shared_wdir+'gcloud', 'w') as gcpfile:
        gcpfile.write(tempv)
    # Add the path to the credentials to the variables sent to Terraform.
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=shared_wdir+'gcloud')
    # If the keys already exist don't recreate them or else you might not be able to access a resource you
    # previously created but havent set the password on.
else:
    print('GCP credential file exists already, skipping....')
    # Add the path to the credentials to the variables sent to Terraform.
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=shared_wdir+'gcloud')

# If the variable is set to apply then create the environment and check for Panorama availabliity
if tfcommand == 'apply':

    a_variables = {
        'p_ip': os.environ.get('Panorama_IP'),
    }

    ansible_variables = "\"password="+os.environ.get('PASSWORD')+"\""

    env = Environment(loader=FileSystemLoader('.'))
    inventory_template = env.get_template('inventory.txt')
    primary_inventory = inventory_template.render(a_variables)
    with open("inventory.yml", "w") as fh:
        fh.write(primary_inventory)

    bootstrap_key = open(str(path.parents[0])+'/gcp_sharedvpc_deploy/key', 'r')
    # Add the boostrap key to the variables sent to Terraform.
    variables.update(TF_VAR_panorama_bootstrap_key=bootstrap_key.read())

    # Generate a new RSA keypair to use to SSH to the VM. If you are using your own automation outside of
    # Panhandler then you should use your own keys.
    if os.path.exists(shared_wdir+'id_rsa') is True:
        print('Crypto Key exists already, skipping....')
        public_key = open(shared_wdir+'pub', 'r')
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

    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook commit.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

# If the variable is destroy, then destroy the environment and remove the SSH keys.
elif tfcommand == 'destroy':
    variables.update(GOOGLE_APPLICATION_CREDENTIALS=shared_wdir+'gcloud')
    variables.update(TF_VAR_ra_key="")
    container = client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform destroy -auto-approve -no-color -input=false',
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

sys.exit(0)
