"""Resource definition for the bot application."""
# TODO: AWS secrets/config setup
from pathlib import Path

import pulumi
import pulumi_aws as aws

# Retrieve the current stack name
STACK_NAME = pulumi.get_stack()

# Use the stack name to conditionally change program behavior
if STACK_NAME == "dev":
    pulumi.log.info("Running in the 'dev' stack.")
    env_file = Path("..") / ".env.dev"
else:
    if STACK_NAME != "prod":
        pulumi.log.warning("Unknown stack name, defaulting to prod.")
    pulumi.log.info("Running in the 'prod' stack.")
    env_file = Path("..") / ".env"

# Get the Pulumi config object
cfg = pulumi.Config()
cfg.require("MODAL_USER_NAME")
cfg.require_secret("DISCORD_AUTH")

GIT_ORG = "the-full-stack"
GIT_REPO = "ask-fsdl"
GIT_BRANCH = "main" if STACK_NAME == "prod" else "charles/pulumi"
GIT_URI = f"https://github.com/{GIT_ORG}/{GIT_REPO}.git"

# allow inbound SSH access
ssh_ingress_rule = aws.ec2.SecurityGroupIngressArgs(
    protocol="tcp",
    from_port=22,  # Allow SSH access
    to_port=22,
    cidr_blocks=["0.0.0.0/0"],  # from all IPs
)

# open outbound traffic
open_egress_rule = aws.ec2.SecurityGroupEgressArgs(
    protocol="-1",  # Allow all protocols
    from_port=0,  # on all ports
    to_port=0,
    cidr_blocks=["0.0.0.0/0"],  # to all IPs
)

security_group = aws.ec2.SecurityGroup(
    "bot-sg",
    ingress=[ssh_ingress_rule],
    egress=[open_egress_rule],
)


def config_as_env():
    """Return the config elements as environment variables, .env style."""
    # these will be plaintext in the internal Pulumi state.
    # for greater security we could use Pulumi's secret management.
    sensitive_keys = ["DISCORD_AUTH", "DISCORD_AUTH_DEV", "DISCORD_MAINTAINER_ID"]
    keys = ["MODAL_USER_NAME"] + sensitive_keys
    return "\n".join([f"{key}={cfg.get(key)}" for key in keys])


def build_startup_script():
    # write the startup script for the EC2 instance
    script = "#!/bin/bash\n"
    script += "sudo yum update -y\n"  # update yum, package manager for amazon linux
    script += "sudo yum install -y git\n"  # install git for cloning the repo
    script += "sudo amazon-linux-extras install -y python3.8\n"  # install recent python
    script += "git clone -b {GIT_BRANCH} {GIT_URI}\n"  # clone the repo
    script += "cd ask-fsdl\n"  # change directory into the repo
    script += f"""echo "{config_as_env()}" >> .env\n"""  # write the config file
    script += "python3.8 -m pip install -r requirements.txt\n"  # install dependencies
    script += "python3.8 bot/run.py"  # run the Discord bot
    script += "--dev\n" if STACK_NAME == "dev" else "\n"  # in dev mode if in dev stack

    return script


# Create an AWS EC2 instance
instance = aws.ec2.Instance(
    "bot-server",
    instance_type="t2.micro",
    ami="ami-0ceecbb0f30a902a6",
    key_name="fsdl-webserver-keys",  # TODO: handle keygen with aws.ec2.KeyPair
    user_data=build_startup_script(),
    user_data_replace_on_change=True,  # reprovision if user_data changes
    vpc_security_group_ids=[security_group.id],
)

# Export the public IP of the EC2 instance for convenience
pulumi.export("bot-public-ip", instance.public_ip)
