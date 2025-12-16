from setuptools import setup, find_packages

setup(
    name="lynch-stock-screener-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "typer[all]>=0.9.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "bag=cli.bag:app",
        ],
    },
)
