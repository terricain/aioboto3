import importlib.machinery
import importlib.util
import setuptools
import pkg_resources
import requests
import sys
import os
from github import Github


def extract_values_from_setuptools():
    # Wont work if setup.py doesnt use setuptools
    loader = importlib.machinery.SourceFileLoader('tmp', 'setup.py')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)

    setup_results = {}

    def fakesetup(**kwargs):
        setup_results.update(kwargs)

    setuptools.setup = fakesetup
    loader.exec_module(mod)
    return setup_results


# Get current required version for aiobotocore
print('Getting aiobotocore dependency version')
setup_kwargs = extract_values_from_setuptools()
install_requires = [dep for dep in pkg_resources.parse_requirements(setup_kwargs['install_requires']) if dep.name == 'aiobotocore']
aiobotocore_dep = install_requires[0]
print('Found: {0}'.format(aiobotocore_dep))

# Get latest aiobotocore verison
print('Getting aiobotocore current version')
resp = requests.get('https://pypi.org/pypi/aiobotocore/json').json()
current_aiobotocore_version = resp['info']['version']
current_aiobotocore_version = '2.0.0'
print('Current aiobotocore version: {0}'.format(current_aiobotocore_version))

if current_aiobotocore_version in aiobotocore_dep:
    print('We\'re good, skip')
    sys.exit(38)  # Currently github have removed the option to exit early but not mark as failed

# By this point we're going to open a pr
# Check that PR isnt already open for this

g = Github(os.environ['GITHUB_TOKEN'])
repo = g.get_repo('terrycain/aioboto3')
pulls = repo.get_pulls(state='open')
for pr in pulls:
    print()



sys.exit(1)

# update setup.py
print('Updating setup.py')
search = str(aiobotocore_dep)
replace = search.replace(str(aiobotocore_dep.specifier), '') + '==' + current_aiobotocore_version  # Does aiobotocore[boto3] + == + version
with open('setup.py', 'r') as fp:
    new_setup_py = fp.read().replace(search, replace)
with open('setup.py', 'w') as fp:
    fp.write(new_setup_py)

# update pipfile
print('Updating Pipfile')
search = str(aiobotocore_dep.specifier)
replace = '==' + current_aiobotocore_version
with open('Pipfile', 'r') as fp:
    new_pipfile = ''
    for line in fp:
        if line.startswith('aiobotocore'):
            line = line.replace(search, replace)
        new_pipfile += line
with open('Pipfile', 'w') as fp:
    fp.write(new_pipfile)
