from aws_cdk import core as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk.aws_elasticloadbalancingv2 import ApplicationProtocol
from aws_cdk import (core, aws_ec2 as ec2, aws_ecs as ecs,
                     aws_ecs_patterns as ecs_patterns)
import aws_cdk.aws_elasticloadbalancingv2 as elbv2

from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as secretsmanager
import aws_cdk.aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_certificatemanager as acm
import json as JSON



class PlanAptStack(cdk.Stack):
    def __init__(self, scope, construct_id, **kwargs):
        self._vpc_id = kwargs.pop('vpc_id')

        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc.from_lookup(self, "PlanAptVPC",
            vpc_id=self._vpc_id
        )

        cluster = ecs.Cluster(self, "PlanAptCluster", vpc=vpc)
        ecr_repository = ecr.Repository(self, "AptTestRepo", repository_name="apt-test", image_scan_on_push=True)

        fargate_task_definition = ecs.FargateTaskDefinition(self, "AptTestTaskDef",
            memory_limit_mib=2048,
            cpu=1024
        )

        fargate_task_definition.add_container("apttest",
            image=ecs.ContainerImage.from_registry(f"{ecr_repository.repository_uri}:latest"),
            port_mappings=[{"containerPort": 3000}],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="apttest"),
        )
        fargate_task_definition.add_to_execution_role_policy(iam.PolicyStatement(
                resources=["*"],
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetRepositoryPolicy",
                    "ecr:DescribeRepositories",
                    "ecr:ListImages",
                    "ecr:DescribeImages",
                    "ecr:BatchGetImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:PutImage",
                    "secretsmanager:GetSecretValue"
                    ]
                )
        )

        nlb_subnets = ec2.SubnetSelection(
                subnets=[ec2.Subnet.from_subnet_id(self, "DBSubnetB","subnet-04bc43815ae89c87f"), ec2.Subnet.from_subnet_id(self, "DBSubnetA", "subnet-0aa6c18b4f7ac05a3")]
                )
        lb = elbv2.NetworkLoadBalancer(self, "NetworkLB",
            vpc=vpc,
            internet_facing=False,
            vpc_subnets=nlb_subnets
        )

        ecs_service = ecs_patterns.NetworkLoadBalancedFargateService(self, "AptTestServiceNlb",
            assign_public_ip=False,
            cluster=cluster,
            cpu=1024,
            desired_count=1,
            task_definition=fargate_task_definition,
            load_balancer=lb,
            memory_limit_mib=2048,
            )
        service = ecs_service.service
        service.connections.allow_internally(ec2.Port.tcp(3000))
        
        # ssh1-mgt1
        service.connections.security_groups[0].add_ingress_rule(
                peer=ec2.Peer.ipv4("10.10.10.94/32"),
                connection=ec2.Port.tcp(3000),
                )
        # ssh2-mgt1
        service.connections.security_groups[0].add_ingress_rule(
                peer=ec2.Peer.ipv4("10.10.20.118/32"),
                connection=ec2.Port.tcp(3000),
                )
        # ssh3-mgt1
        service.connections.security_groups[0].add_ingress_rule(
                peer=ec2.Peer.ipv4("10.10.10.147/32"),
                connection=ec2.Port.tcp(3000),
                )
        # rdp1-mgt1
        service.connections.security_groups[0].add_ingress_rule(
                peer=ec2.Peer.ipv4("10.10.10.206/32"),
                connection=ec2.Port.tcp(3000),
                )
        service.connections.security_groups[0].add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(3000),

                )

        scaling = ecs_service.service.auto_scale_task_count(max_capacity=5)
        scaling.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=50
        )
        
        # ECR Build task
        ecr_build = codebuild.PipelineProject(self, 
                            'PlanAptBuild',
                            vpc=vpc, 
                            environment=codebuild.BuildEnvironment(privileged=True, build_image=codebuild.LinuxBuildImage.STANDARD_2_0),
                            environment_variables=dict(
                                IMAGE_REPO_NAME=codebuild.BuildEnvironmentVariable(value=ecr_repository.repository_name)
                            ),
                            build_spec=codebuild.BuildSpec.from_object(dict(
                                version="0.2",
                                phases=dict(
                                    install=dict(
                                        commands=[
                                            "apt-get install jq -y",
                                        ]),
                                    build=dict(commands=[
                                               "ContainerName=\"planapt\"",
                                               "ImageURI=$(cat imageDetail.json | jq -r '.ImageURI')",
                                               "printf '[{\"name\":\"CONTAINER_NAME\",\"imageUri\":\"IMAGE_URI\"}]' > imagedefinitions.json",
                                               "sed -i -e \"s|CONTAINER_NAME|$ContainerName|g\" imagedefinitions.json",
                                               "sed -i -e \"s|IMAGE_URI|$ImageURI|g\" imagedefinitions.json",
                                               "cat imagedefinitions.json"
                                        ])),
                                artifacts={
                                    "files": [
                                        "imagedefinitions.json"]},
                            )
                            )
                            )
        # ECR CodeBuild Task permissions
        ecr_build.add_to_role_policy(iam.PolicyStatement(
                resources=["*"],
                actions=[
                    "secretsmanager:GetSecretValue",
                    "ecr:GetAuthorizationToken",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    ]
                )
        )

        code_commit_repo = codecommit.Repository(self, "CodeCommitRepo",
            repository_name="apttest"
        )

        source_output = codepipeline.Artifact()
        source_action = codepipeline_actions.CodeCommitSourceAction(
            action_name="AptTestSource",
            repository=code_commit_repo,
            branch="main",
            output=source_output,
        )        

        ecr_build_output = codepipeline.Artifact("AptTestBuildOutput")
        ecs_deployment = codepipeline_actions.EcsDeployAction(action_name="DeployAptTest", 
                                                              image_file=codepipeline.ArtifactPath(artifact=ecr_build_output, file_name="imagedefinitions.json"),
                                                              service=ecs_service.service)
        ecr_build_action = codepipeline_actions.CodeBuildAction(
                            action_name="ECR_Build",
                            project=ecr_build,
                            input=source_output,
                            outputs=[ecr_build_output])

        ecr_pipeline = codepipeline.Pipeline(self, "EcrPipeline",
            stages=[
                codepipeline.StageProps(stage_name="Source",
                    actions=[
                            source_action,
                            ]),
                codepipeline.StageProps(stage_name="Build",
                    actions=[
                            ecr_build_action
                            ]
                    ),
                codepipeline.StageProps(stage_name="Deploy",
                    actions=[
                        ecs_deployment
                        ]
                    )
            ]
        )



class Stage(cdk.Stage):

    def __init__(self, scope, id, **kwargs):
        self._vpc_id = "vpc-0f4522eb71211897f"

        super().__init__(scope, id, **kwargs)
        aptTestStack = aptTestStack(self, 
                                    f"aptTestStage", 
                                    synthesizer=cdk.DefaultStackSynthesizer(), 
                                    vpc_id=self._vpc_id)
