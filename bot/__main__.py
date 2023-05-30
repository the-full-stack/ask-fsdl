"""Resource definition for the bot application."""
import pulumi
import pulumi_aws as aws

GIT_REPO = "https://github.com/the-full-stack/ask-fsdl.git"

# TODO: can I just configure the security group and call it a day?
# Create a new VPC
vpc = aws.ec2.Vpc("ask-fsdl-vpc", cidr_block="10.0.0.0/16")

# Create a new public subnet
subnet = aws.ec2.Subnet(
    "ask-fsdl-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.0.0/24",
    availability_zone="us-west-2a",
)

# Create an internet gateway
gateway = aws.ec2.InternetGateway("ask-fsdl-internet-gateway", vpc_id=vpc.id)

# Create a route table
route_table = aws.ec2.RouteTable(
    "ask-fsdl-route-table",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=gateway.id,
        ),
    ],
)

# Associate the route table with the subnet
association = aws.ec2.RouteTableAssociation(
    "ask-fsdl-route-table-association",
    subnet_id=subnet.id,
    route_table_id=route_table.id,
)


# allow SSH access
security_group = aws.ec2.SecurityGroup(
    "ask-fsdl-ssh-access",
    vpc_id=vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=22,
            to_port=22,
            cidr_blocks=["0.0.0.0/0"],  # Allow SSH access from all IPs
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",  # Allow all protocols
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],  # Allow all outbound traffic
        ),
    ],
)

# TODO: handle secrets -- scp from local?
# Create an AWS EC2 instance
instance = aws.ec2.Instance(
    "ask-fsdl-bot",
    instance_type="t2.micro",
    ami="ami-0ceecbb0f30a902a6",
    subnet_id=subnet.id,
    key_name="fsdl-webserver-keys",  # TODO: handle keygen
    # TODO: is there a better AMI for this? maybe with Ubuntu?
    user_data=f"""#!/bin/bash
    sudo yum update -y
    sudo yum install -y git
    sudo amazon-linux-extras install -y python3.8
    git clone {GIT_REPO}
    cd ask-fsdl
    python3.8 -m pip install -r requirements.txt
    python3.8 bot/run_bot.py --dev
    """,
    vpc_security_group_ids=[security_group.id],
)
# TODO: try this:
# alias python='python3.8'
# and go back to using the make commands

# Create a public IP address for the instance
eip = aws.ec2.Eip("ask-fsdl-instance-eip", instance=instance.id, vpc=True)

# Create a route to the internet gateway
route = aws.ec2.Route(
    "ask-fsdl-route",
    route_table_id=route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=gateway.id,
)

# Export the public IP of the EC2 instance for convenience
pulumi.export("public_ip", instance.public_ip)
