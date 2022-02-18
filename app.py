#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import core


from usace_mars.usace_mars_stack import UsaceMarsStack



app = core.App()
env = core.Environment(account="379454761305", region="us-gov-west-1")
UsaceMarsStack(app, "UsaceMarsStack", env=env)

app.synth()
