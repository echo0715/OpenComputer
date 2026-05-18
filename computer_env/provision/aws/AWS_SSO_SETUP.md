# AWS CLI SSO Setup

Use this guide only if the OpenComputer AWS `remote_docker` workflow will authenticate through AWS IAM Identity Center (AWS SSO).

## What You Need From Your AWS Admin

Before local CLI setup, make sure you have all of the following:

- an IAM Identity Center start URL or issuer URL
- the IAM Identity Center Region
- an assigned AWS account
- an assigned role or permission set for that account

For a first OpenComputer setup, `AdministratorAccess` is the fastest way to validate the workflow. Tighten permissions later if needed.

## Admin-Side Checklist

If your organization has not already done this, an AWS administrator must:

1. Enable IAM Identity Center.
2. Create or sync the user and, optionally, a group.
3. Assign that user or group to the target AWS account.
4. Attach a permission set to that assignment.
5. Send the user the start URL or issuer URL, the IAM Identity Center Region, the AWS account, and the role name.

If any of those are missing, `aws configure sso` and `aws sso login` will not be enough.

## Local Machine Setup

### 1. Install AWS CLI v2

Install AWS CLI v2 and verify it:

```bash
aws --version
```

### 2. Configure the SSO Profile

Create a local profile:

```bash
aws configure sso --profile opencomputer-dev
```

Typical answers:

- SSO session name: any local name, for example `opencomputer-sso`
- SSO start URL or issuer URL: from your admin
- SSO Region: the Region where IAM Identity Center is enabled
- Registration scopes: `sso:account:access`
- AWS account: choose the target account
- Role: choose the assigned role or permission set
- Default client Region: the workload Region you will use later, for example `us-east-1`
- Default output format: `json`

### 3. Sign In

```bash
aws sso login --profile opencomputer-dev
```

If this is your first login, you may need to activate the invitation, set a password, or complete MFA.

### 4. Verify the Profile

```bash
aws sts get-caller-identity --profile opencomputer-dev
```

This command should return the account and caller ARN for the intended role.

### 5. Write the Values OpenComputer Uses

After the profile works, add these to the repository root `.env`:

```bash
AWS_PROFILE=opencomputer-dev
AWS_REGION=us-east-1
```

Important: the `aws` CLI does not read the repository `.env`. OpenComputer's Python provisioning scripts do. That is why the verification step above uses `--profile` explicitly.

## Common Failure Cases

### `aws configure sso` cannot be completed

Likely causes:

- you do not have the start URL or issuer URL yet
- you do not know the IAM Identity Center Region
- IAM Identity Center has not been enabled yet

### `aws sso login` succeeds, but no AWS account or role is available

Likely causes:

- the user or group was never assigned to the AWS account
- the assignment exists, but no permission set was attached
- an external IdP user or group has not synced yet

### `aws sts get-caller-identity --profile ...` fails after it worked before

Most likely the SSO session expired. Re-run:

```bash
aws sso login --profile opencomputer-dev
```

### You authenticated, but to the wrong account or role

Re-run `aws configure sso --profile opencomputer-dev` and select the intended account and role.

## References

- [Configuring IAM Identity Center authentication with the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [Getting started with IAM Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/getting-started.html)
