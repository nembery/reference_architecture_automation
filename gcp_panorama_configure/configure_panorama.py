import os
import socket
from docker import DockerClient
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('.'))

variables = {
    'p_ip': os.environ.get('Panorama_IP'),
    "p_serial": os.environ.get('Primary_Serial'),
    "p_peer": os.environ.get('Secondary_Private_IP'),
    "s_ip": os.environ.get('Secondary_IP'),
    "s_serial": os.environ.get('Secondary_Serial'),
    "s_peer": os.environ.get('Primary_Private_IP')
}

ansible_variables = "\"password="+os.environ.get('PASSWORD')+" primary_otp="+os.environ.get('OTP')+" secondary_otp="+os.environ.get('Secondary_OTP')+"\""

if os.environ.get('enable_ha') == "true":
    inventory_template = env.get_template('ha_inventory.txt')
    secondary_inventory = inventory_template.render(variables)
    with open("inventory.yml", "w") as fh:
        fh.write(secondary_inventory)
else:
    inventory_template = env.get_template('inventory.txt')
    primary_inventory = inventory_template.render(variables)
    with open("inventory.yml", "w") as fh:
        fh.write(primary_inventory)

client = DockerClient()
container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook platformsettings.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
# Monitor the log so that the user can see the console output during the run versus waiting until it is complete. The container stops and is removed once the run is complete and this loop will exit at that time.
for line in container.logs(stream=True):
    print(line.decode('utf-8').strip())

# Run the appropriate Ansible playbook based on if the user selected HA or not
if os.environ.get('enable_ha') == "true":
    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook ha.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
else:
    container = client.containers.run('paloaltonetworks/pan-ansible', "ansible-playbook otp.yml -e "+ansible_variables+" -i inventory.yml", auto_remove=True, volumes_from=socket.gethostname(), working_dir=os.getcwd(), user=os.getuid(), detach=True)
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
