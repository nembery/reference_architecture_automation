import os
import socket
from pathlib import Path

from docker import DockerClient

path = Path(os.getcwd())
wdir = str(path.parents[0]) + '/terraform/azure/panorama/'

print('Logging in to Azure using device code...')

client = DockerClient()

volume = client.volumes.create(name='terraform-azure')

# ensure we set permissions on this volume to the uid we will be using throughout
cleanup = client.containers.run('alpine', 'chown -R %s /home/terraform/.azure' % os.getuid(),
                                volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}}
                                )

subscription = os.environ.get('SUBSCRIPTION')

# home must be set manually, as containers may not have an entry in etc passwd for all possible uid
e = dict(HOME="/home/terraform")
container = client.containers.run('paloaltonetworks/terraform-azure', 'az login --use-device-code', auto_remove=True,
                                  volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                  volumes_from=socket.gethostname(), working_dir=wdir,
                                  user=os.getuid(), environment=e,
                                  detach=True)
# Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
# The container stops and is removed once the run is complete and this loop will exit at that time.
for line in container.logs(stream=True):
    print(line.decode('utf-8').strip())

if subscription != '':
    print('Set the subscription...')
    container = client.containers.run('paloaltonetworks/terraform-azure',
                                      'az account set --subscription=' + subscription, auto_remove=True,
                                      volumes={'terraform-azure': {'bind': '/home/terraform/.azure/', 'mode': 'rw'}},
                                      volumes_from=socket.gethostname(), working_dir=wdir,
                                      user=os.getuid(), environment=e,
                                      detach=True)
    # Monitor the log so that the user can see the console output during the run versus waiting until it is complete.
    # The container stops and is removed once the run is complete and this loop will exit at that time.
    for line in container.logs(stream=True):
        print(line.decode('utf-8').strip())
    print('Done.')

pass
