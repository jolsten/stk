# -*- coding: utf-8 -*-
import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name="stk-jkolste",
    version="0.1.1",
    author="Jonathan Olsten",
    author_email="jonathan.olsten@us.af.mil",
    description="A succinct package to interact with AGI's Systems ToolKit (STK) via the Connect command interface",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jolsten/stk",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)