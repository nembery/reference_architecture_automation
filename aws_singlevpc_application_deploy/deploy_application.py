import sys
import os
import socket
from pathlib import Path
from docker import DockerClient
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('.'))

# I am deploying the application seperate from the security because the firewall's have to be up and
# operational for the web server instances to reach out to the repository to cloud install apache.
# If you are using an AMI that has all the right software installed you can provision the application
# at the same time as the VM-Series firewalls.

# Pull in the AWS Provider variables. These are set in the Skillet Environment and are hidden variables so the
# user doesn't need to adjust them everytime.
variables = dict(AWS_ACCESS_KEY_ID=os.environ.get('AWS_ACCESS_KEY_ID'), PANOS_PASSWORD=os.environ.get('PASSWORD'),
                 AWS_SECRET_ACCESS_KEY=os.environ.get('AWS_SECRET_ACCESS_KEY'), PANOS_USERNAME='admin', TF_IN_AUTOMATION='True')
variables.update(TF_VAR_deployment_name=os.environ.get('DEPLOYMENT_NAME'), TF_VAR_aws_region=os.environ.get('AWS_REGION'))

if os.environ.get('AWS_SESSION_TOKEN') != "":
    variables.update(AWS_SESSION_TOKEN=os.environ.get('AWS_SESSION_TOKEN'))

# A variable the defines if we are creating or destroying the environment via terraform. Set in the dropdown
# on Panhandler.
tfcommand = (os.environ.get('Init'))

# Define the working directory for the container as the terraform directory and not the directory of the skillet.
path = Path(os.getcwd())
wdir = str(path.parents[0])+'/terraform/aws/application_deploy/'

a_variables = {
    'p_ip': os.environ.get('Panorama_IP'),
}

ansible_variables = "\"password="+os.environ.get('PASSWORD')+"\""

inventory_template = env.get_template('inventory.txt')
primary_inventory = inventory_template.render(a_variables)
with open("inventory.yml", "w") as fh:
    fh.write(primary_inventory)

# The script uses a terraform docker container to run the terraform plan. The script uses the docker host that
# panhandler is running on to run the new conatiner. /var/lib/docker.sock must be mounted on panhandler
client = DockerClient()

# If the variable is set to apply then create the environment and check for Panorama availabliity
if tfcommand == 'apply':
    # Init terraform with the modules and providers. The continer will have the some volumes as Panhandler.
    # This allows it to access the files Panhandler downloaded from the GIT repo.
    container = client.containers.run('hashicorp/terraform:0.12.29', 'init -no-color -input=false', auto_remove=True,
                                      volumes_from=socket.gethostname(), working_dir=wdir,user=os.getuid(),
                                      environment=variables, detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

    # Run terraform apply
    container = client.containers.run('hashicorp/terraform:0.12.29', 'apply -auto-approve -no-color -input=false',
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    # Commit and push the changes in Panorama
    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook commit.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())


# If the variable is destroy, then destroy the environment and commit and push the changes in Panorama.
elif tfcommand == 'destroy':
    container = client.containers.run('hashicorp/terraform:0.12.29', 'destroy -auto-approve -no-color -input=false',
                                      auto_remove=True, volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(),
                                      environment=variables, detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook commit.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())

sys.exit(0)
