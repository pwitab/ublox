#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'pyserial',
]

setup(
    name='ublox',
    version='0.1.0', python_requires='~=3.6',
    description="Python library for U-blox cellular modules.",
    long_description=readme + '\n\n' + history,
    author="Henrik Palmlund Wahlgren @ Palmlund Wahlgren Innovative Technology AB",
    author_email='henrik@pwit.se',
    url='https://www.pwit.se',
    packages=[
        'ublox',
    ],
    include_package_data=True,
    install_requires=requirements,

    license="MIT",
    zip_safe=False,
    keywords='NB-IoT, LTE-M',
    classifiers=[

    ],
)