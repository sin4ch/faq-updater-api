# setup_secrets.py
import boto3
import json
import getpass
import argparse
import os

# --- Configuration ---
DEFAULT_SECRET_NAME = "FaqUpdater/TwilioAuthToken"
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION") # Try to get from env
CONFIG_FILE = "samconfig.toml"
# --- End Configuration ---

def get_aws_region(args_region):
    """Gets the AWS region, prompting if necessary."""
    if args_region:
        return args_region
    if DEFAULT_REGION:
        use_default = input(f"Use default AWS region '{DEFAULT_REGION}'? (y/n): ").lower()
        if use_default == 'y':
            return DEFAULT_REGION
    while True:
        region = input("Enter the AWS region for deployment (e.g., us-east-1): ")
        if region:
            return region
        print("Region cannot be empty.")


def create_or_update_secret(secrets_client, secret_name, secret_value):
    """Creates or updates a secret in AWS Secrets Manager."""
    try:
        print(f"Attempting to create secret '{secret_name}'...")
        response = secrets_client.create_secret(
            Name=secret_name,
            Description="Twilio Auth Token for FAQ Updater API",
            SecretString=secret_value
        )
        print(f"Successfully created secret '{secret_name}'.")
        return response['ARN']
    except secrets_client.exceptions.ResourceExistsException:
        print(f"Secret '{secret_name}' already exists. Attempting to update...")
        try:
            response = secrets_client.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_value
            )
            print(f"Successfully updated secret '{secret_name}'.")
            # Need to describe to get ARN after update if it existed
            desc_response = secrets_client.describe_secret(SecretId=secret_name)
            return desc_response['ARN']
        except Exception as update_err:
            print(f"Error updating secret: {update_err}")
            return None
    except Exception as create_err:
        print(f"Error creating secret: {create_err}")
        return None

def update_samconfig(region, secret_arn, stack_name):
    """Updates samconfig.toml with deployment parameters."""
    config_lines = []
    updated_params = False
    param_string = f'TwilioAuthTokenSecretArn="{secret_arn}"'

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config_lines = f.readlines()

    # Basic TOML parsing/updating (replace if a proper library is available/desired)
    new_config = []
    in_default_deploy_parameters = False
    found_params = False

    for line in config_lines:
        stripped_line = line.strip()
        if stripped_line.startswith('[default.deploy.parameters]'):
            in_default_deploy_parameters = True
            new_config.append(line)
        elif in_default_deploy_parameters and stripped_line.startswith('['): # Start of next section
             in_default_deploy_parameters = False
             # Add parameters if they weren't found in the section
             if not found_params:
                 new_config.append(f'stack_name = "{stack_name}"\n')
                 new_config.append(f'region = "{region}"\n')
                 new_config.append(f'parameter_overrides = "{param_string}"\n')
                 updated_params = True
             new_config.append(line)
        elif in_default_deploy_parameters:
            if stripped_line.startswith('stack_name'):
                 new_config.append(f'stack_name = "{stack_name}"\n')
                 found_params = True # Mark that we are handling params
            elif stripped_line.startswith('region'):
                 new_config.append(f'region = "{region}"\n')
            elif stripped_line.startswith('parameter_overrides'):
                 # Very basic override handling - assumes only this parameter
                 new_config.append(f'parameter_overrides = "{param_string}"\n')
            else:
                 new_config.append(line) # Keep other parameters
        else:
            new_config.append(line) # Keep lines outside the target section

    # If the section or file didn't exist
    if not updated_params and not found_params:
         if not any(line.strip().startswith('[default.deploy.parameters]') for line in new_config):
              new_config.append('\n[default.deploy.parameters]\n')
         new_config.append(f'stack_name = "{stack_name}"\n')
         new_config.append(f'region = "{region}"\n')
         new_config.append(f'parameter_overrides = "{param_string}"\n')


    try:
        with open(CONFIG_FILE, 'w') as f:
            f.writelines(new_config)
        print(f"Updated '{CONFIG_FILE}' with deployment parameters.")
    except IOError as e:
        print(f"Error writing to '{CONFIG_FILE}': {e}")


def main():
    parser = argparse.ArgumentParser(description="Setup secrets and config for FAQ Updater API.")
    parser.add_argument("--secret-name", default=DEFAULT_SECRET_NAME, help=f"Name for the secret in AWS Secrets Manager (default: {DEFAULT_SECRET_NAME})")
    parser.add_argument("--region", help="AWS region for deployment and secret creation.")
    parser.add_argument("--stack-name", default="faq-updater-api", help="Default stack name for samconfig.toml (default: faq-updater-api)")
    parser.add_argument("--non-interactive", action="store_true", help="Attempt non-interactive setup (requires TWILIO_AUTH_TOKEN env var)")

    args = parser.parse_args()

    # --- Get Region ---
    aws_region = get_aws_region(args.region)
    if not aws_region:
        print("Could not determine AWS region. Exiting.")
        return

    print(f"Using AWS region: {aws_region}")
    session = boto3.Session(region_name=aws_region)
    secrets_client = session.client('secretsmanager')

    # --- Get Twilio Token ---
    twilio_token = None
    if args.non_interactive:
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        if not twilio_token:
            print("Error: --non-interactive requires the TWILIO_AUTH_TOKEN environment variable to be set.")
            return
        print("Using Twilio Auth Token from environment variable.")
    else:
        print("\nEnter your Twilio Account SID's Auth Token.")
        print("It will be stored securely in AWS Secrets Manager.")
        twilio_token = getpass.getpass("Twilio Auth Token: ")
        if not twilio_token:
            print("Twilio Auth Token cannot be empty. Exiting.")
            return

    # --- Create/Update Secret ---
    secret_arn = create_or_update_secret(secrets_client, args.secret_name, twilio_token)

    if not secret_arn:
        print("Failed to create or update the secret in AWS Secrets Manager. Please check permissions and try again.")
        return

    print("-" * 30)
    print("Secret ARN created/updated:")
    print(secret_arn)
    print("-" * 30)
    print(f"You will need to provide this ARN for the 'TwilioAuthTokenSecretArn' parameter during 'sam deploy --guided',")
    print(f"OR it can be automatically used if you run 'sam deploy' after this script updates '{CONFIG_FILE}'.")
    print("-" * 30)


    # --- Update samconfig.toml ---
    if not args.non_interactive:
        update_conf = input(f"Update '{CONFIG_FILE}' with region, stack name, and secret ARN for easier deployment? (y/n): ").lower()
        if update_conf == 'y':
             update_samconfig(aws_region, secret_arn, args.stack_name)
        else:
             print(f"Skipping update to '{CONFIG_FILE}'.")
    elif secret_arn: # Update config in non-interactive mode if secret succeeded
         update_samconfig(aws_region, secret_arn, args.stack_name)


if __name__ == "__main__":
    main()