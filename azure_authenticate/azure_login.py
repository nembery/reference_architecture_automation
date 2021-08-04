import os
import socket
from docker import DockerClient
from pathlib import Path

path = Path(os.getcwd())
wdir = str(path.parents[0])+'/terraform/azure/panorama/'

print('Logging in to Azure using device code...')

client = DockerClient()

volume = client.volumes.create(name='terraform-azure')

subscription = os.environ.get('SUBSCRIPTION')

container = client.containers.run('paloaltonetworks/terraform-azure', 'az login --use-device-code', auto_remove=True,
                                    volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                    volumes_from=socket.gethostname(), working_dir=wdir,
                                  user=os.getuid(),
                                    detach=True)
# Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
# The container stops and is removed once the run is complete and this loop will exit at that time.
for line in container.logs(stream=True):
    print(line.decode('utf-8').strip())

if subscription != '':
    print('Set the subscription...')
    container = client.containers.run('paloaltonetworks/terraform-azure', 'az account set --subscription='+subscription, auto_remove=True,
                                        volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                        volumes_from=socket.gethostname(), working_dir=wdir,
                                      user=os.getuid(),
                                        detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    print('Done.')

pass
