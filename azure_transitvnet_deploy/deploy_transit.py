import sys
import os
import socket
import requests
from pathlib import Path
from docker import DockerClient

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('.'))

# This setting change removes the warnings when the script tries to connect to Panorama and check its availability
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Pull in the AWS Provider variables. These are set in the Skillet Environment and are hidden variables so the
# user doesn't need to adjust them everytime.
variables = dict(PANOS_PASSWORD=os.environ.get('PASSWORD'), TF_VAR_password=os.environ.get('PASSWORD'),
                 PANOS_USERNAME='refarchadmin', TF_IN_AUTOMATION='True', HOME='/home/terraform')
variables.update(TF_VAR_deployment_name=os.environ.get('DEPLOYMENT_NAME'), TF_VAR_vpc_cidr_block=os.environ.get(
                'transit_cidr_block'), TF_VAR_azure_region=os.environ.get('AZURE_REGION'), TF_VAR_authcode=os.environ.get('authcode'))
                # TF_VAR_vpn_peer=os.environ.get('vpn_peer'), TF_VAR_vpn_as=os.environ.get('vpn_as'), TF_VAR_vpn_psk=os.environ.get('vpn_psk'))
# A variable the defines if we are creating or destroying the environment via terraform. Set in the dropdown
# on Panhandler.
tfcommand = (os.environ.get('Init'))

# Define the working directory for the container as the terraform directory and not the directory of the skillet.
path = Path(os.getcwd())
wdir = str(path.parents[0])+'/terraform/azure/transit-vnet-deploy/'

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

a_variables = {
    'p_ip': os.environ.get('Panorama_IP'),
}

ansible_variables = "\"password="+os.environ.get('PASSWORD')+"\""

inventory_template = env.get_template('inventory.txt')
primary_inventory = inventory_template.render(a_variables)
with open("inventory.yml", "w") as fh:
    fh.write(primary_inventory)

# If the variable is set to apply then create the environment and check for Panorama availabliity
if tfcommand == 'apply':

    if os.path.exists('key') is not True:
        container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook panoramasettings.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
        for line in container.logs(stream=True):
            print(line.decode('utf-8').strip())

    bootstrap_key = open('key', 'r')
    # Add the boostrap key to the variables sent to Terraform so it can create the AWS key pair.
    variables.update(TF_VAR_panorama_bootstrap_key=bootstrap_key.read())

    # Init terraform with the modules and providers. The continer will have the some volumes as Panhandler.
    # This allows it to access the files Panhandler downloaded from the GIT repo.
    container = client.containers.run('paloaltonetworks/terraform-azure', 'terraform init -no-color -input=false', auto_remove=True,
                                      volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                      volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    # Run terraform apply
    container = client.containers.run('paloaltonetworks/terraform-azure', 'terraform apply -auto-approve -no-color -input=false',
                                      volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir,
                                      user=os.getuid(),
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
    try:
        bootstrap_key = open('key', 'r')
        variables.update(TF_VAR_panorama_bootstrap_key=bootstrap_key.read())
    except Exception:
        variables.update(TF_VAR_panorama_bootstrap_key=" ")
    # Add the boostrap key to the variables sent to Terraform so it can create the AWS key pair.

    container = client.containers.run('paloaltonetworks/terraform-azure', 'terraform destroy -auto-approve -no-color -input=false',
    #container = client.containers.run('paloaltonetworks/terraform-azure', "terraform state rm aazurerm_storage_share.this",
                                      volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir,
                                      user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    # Remove the SSH keys we used to provision Panorama from the container.

    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook commit.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

    print('Removing local keys....')
    try:
        os.remove('key')
    except Exception:
        print('  There where no keys to remove')

sys.exit(0)
