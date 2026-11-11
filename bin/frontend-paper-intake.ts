#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import {FrontendPaperIntakeStack} from '../lib/frontend-paper-intake-stack';
const app=new cdk.App();
new FrontendPaperIntakeStack(app,'JumpServeFrontendPaperIntakeStack',{env:{account:'395567831870',region:'us-east-1'}});
