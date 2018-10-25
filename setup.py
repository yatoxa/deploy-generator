import os
from setuptools import find_packages, setup


with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='deploy-generator',
    version='0.1',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'deploy=deploy_generator.deploy:main',
        ],
    },
    include_package_data=True,
    install_requires=[
        'pyyaml==3.13',
        'Mako==1.0.7',
    ],
    license='BSD License',
    description='Deploy generator and executor tool.',
    long_description=README,
    url='https://github.com/yatoxa/deploy-generator',
    author='Toxa Yantsen',
    author_email='yatoxa@yatoxa.com'
)
