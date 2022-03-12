from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

with open(path.join(here, "requirements/production.txt"), encoding="utf-8") as f:
    production = f.readlines()

with open(path.join(here, "requirements/development.txt"), encoding="utf-8") as f:
    development = f.readlines()


setup(
    name="genesis",
    version="0.3.1",
    description="Client implementation of FreeSWITCH Event Socket protocol with asyncio",
    include_package_data=True,
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Otoru/Genesis",
    author="Vitor Hugo de Oliveira Vargas",
    author_email="contato@vitoru.dev",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Telecommunications Industry",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Communications :: Telephony",
        "Topic :: Software Development",
    ],
    keywords="ESL, FreeSwitch",
    packages=find_packages(exclude=["tests"]),
    install_requires=production,
    extras_require={"dev": development},
    zip_safe=False,
    project_urls={
        "Bug Reports": "https://github.com/Otoru/Genesis/issues",
        "Source Code": "https://github.com/Otoru/Genesis",
    },
)
