from aws_cdk import (
    aws_iam as iam,
    aws_ecr as ecr,
    core
)
import aws_cdk.aws_codepipeline as codepipeline
import aws_cdk.aws_codebuild as codebuild
import aws_cdk.aws_codepipeline_actions as codepipeline_actions
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_rds as rds
import aws_cdk.aws_s3 as s3
from aws_cdk.pipelines import  CdkPipeline,SimpleSynthAction
from .usace_mars_ecs import MarsEcsStage




class UsacePlanAPTStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        oauth = core.SecretValue.secrets_manager("github_token")
        source_artifact = codepipeline.Artifact()


        github_source = codepipeline_actions.GitHubSourceAction(oauth_token=oauth,
                output=source_artifact,
                owner="GTRIGlobal",
                repo="PlanUSACE-APT",
                branch="main",
                action_name="GitSourceAction",
                )


        vpc = ec2.Vpc.from_lookup(self, 
                "VPC",
                vpc_id="vpc-0f4522eb71211897f",
            )

        cloud_assembly_artifact = codepipeline.Artifact()


        pipeline = CdkPipeline(self, "PlanAptPipeline",
            pipeline_name="PlanApt",
            self_mutating=True,
            cloud_assembly_artifact=cloud_assembly_artifact,
            support_docker_assets=True,
            source_action=github_source,
            synth_action=SimpleSynthAction(
                source_artifact=source_artifact,
                cloud_assembly_artifact=cloud_assembly_artifact,
                environment=codebuild.BuildEnvironment(build_image=codebuild.LinuxBuildImage.STANDARD_5_0, privileged=True),
                role_policy_statements=[iam.PolicyStatement(
                    actions=["*"],
                    resources=["*"]
                    )],
                install_commands=[
                    "npm install -g aws-cdk cdk-assume-role-credential-plugin",
                    "python3.9 -m pip install --upgrade pip",
                    "pip3 install -r requirements.txt"
                    ],
                synth_command="cdk synth -v"
            )
        )

        bucket = s3.Bucket(self, "S3ServerBucket", versioned=True, bucket_name="plan-apt-test")

        Stage = PlanAptStage(self,
            f"PlanAptStage",
            env=kwargs['env']
        )
        pipeline.add_application_stage(Stage)
