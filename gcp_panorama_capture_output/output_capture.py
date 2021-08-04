import sys
import os
import socket
import json
from pathlib import Path
from docker import DockerClient

# Pull in the AWS Provider variables. These are set in Panhandler's skillet environment and are hidden variables so the user
# doesn't need to adjust them everytime
path = Path(os.getcwd())
wdir = str(path.parents[0])+'/terraform/gcp/panorama/'
variables = dict(GOOGLE_APPLICATION_CREDENTIALS=wdir+'gcloud', TF_IN_AUTOMATION='True')

client = DockerClient()
# Capture the External IP address of Panorama from the Terraform output
eip = json.loads(client.containers.run('paloaltonetworks/terraform-gcloud', 'terraform output -json -no-color', auto_remove=True,
                                       volumes_from=socket.gethostname(), working_dir=wdir, user=os.getuid(), environment=variables).decode('utf-8'))
panorama_ip = (eip['primary_eip']['value'])
panorama_private_ip = (eip['primary_private_ip']['value'])
secondary_ip = (eip['secondary_eip']['value'])
secondary_private_ip = (eip['secondary_private_ip']['value'])

poutput = dict()
poutput.update(Primary_IP=panorama_ip)
poutput.update(Secondary_IP=secondary_ip)
poutput.update(Primary_Private_IP=panorama_private_ip)
poutput.update(Secondary_Private_IP=secondary_private_ip)
print(json.dumps(poutput))

sys.exit(0)
