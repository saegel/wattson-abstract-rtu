import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="wattson-abstract-rtu",
    version="1.0.0",
    author="Olav Lamberts and Lennart Bader",
    author_email="lennart.bader@fkie.fraunhofer.de",
    description="An abstraction layer for software-based RTU implementations.",
    url="https://github.com/fkie-cad/wattson-abstract-rtu",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)