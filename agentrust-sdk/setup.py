"""
Setup script for Agentrust SDK.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="agentrust-sdk",
    version="1.0.0",
    author="Agentrust Team",
    description="Python SDK for Agentrust Agent Identity and Permission System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agentrust/agentrust",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Security",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.25.0",
        "cryptography>=41.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
        ],
    },
)
