#!/bin/bash

export AWS_PROFILE="big3192-evl-se"
sam build; sam deploy --no-confirm-changeset --profile ${AWS_PROFILE} --parameter-overrides VpcID=vpc-0e3411d0660b0de81  SubnetIDs=subnet-0062068627abfd8d0,subnet-0e925fb0d881ba056,subnet-082fb0ed62052e4f6 SfAWSID=087064826015
