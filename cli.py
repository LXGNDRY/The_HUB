"""
GCP Bot — CLI Entry Point
Usage:
  python cli.py deploy --dir ./my-theme --label summer-drop-v2
  python cli.py versions
  python cli.py rollback --version 20240517T120000Z
  python cli.py download --dest ./downloaded-theme
  python cli.py push-shopify --dir ./my-theme --theme-id 123456789
  python cli.py diff --a 20240517T120000Z --b 20240518T090000Z
"""

import click
from agents.theme_deployment_agent import ThemeDeploymentAgent


@click.group()
def cli():
    """GCP Bot — Theme Deployment Agent CLI"""
    pass


@cli.command()
@click.option("--dir",    required=True,  help="Local path to theme directory")
@click.option("--label",  default=None,   help="Human-readable version label")
def deploy(dir, label):
    """Upload theme to GCS and create a versioned snapshot."""
    agent = ThemeDeploymentAgent()
    version_pfx = agent.upload_theme(dir, label=label)
    click.echo(f"\nVersion prefix: {version_pfx}")


@cli.command()
@click.option("--limit", default=10, help="Max versions to show")
def versions(limit):
    """List recent theme versions stored in GCS."""
    agent = ThemeDeploymentAgent()
    vlist = agent.list_versions(limit=limit)
    if not vlist:
        click.echo("No versions found.")
        return
    click.echo(f"\n{'Version ID':<22} {'Label':<30} {'Files':>6}  Deployed At")
    click.echo("-" * 75)
    for v in vlist:
        click.echo(f"{v['version_id']:<22} {v.get('label',''):<30} {v['file_count']:>6}  {v['deployed_at']}")


@cli.command()
@click.option("--version", required=True, help="Version ID to roll back to (e.g. 20240517T120000Z)")
def rollback(version):
    """Roll back the live GCS snapshot to a previous version."""
    agent = ThemeDeploymentAgent()
    agent.rollback(version)


@cli.command()
@click.option("--dest", required=True, help="Local directory to download live theme into")
def download(dest):
    """Download the current live theme snapshot from GCS."""
    agent = ThemeDeploymentAgent()
    agent.download_live(dest)


@cli.command("push-shopify")
@click.option("--dir",      required=True, help="Local theme directory")
@click.option("--theme-id", required=True, help="Shopify theme ID")
def push_shopify(dir, theme_id):
    """Push local theme files directly to Shopify via Admin API."""
    agent = ThemeDeploymentAgent()
    agent.push_to_shopify(dir, theme_id)


@cli.command()
@click.option("--a", required=True, help="First version ID")
@click.option("--b", required=True, help="Second version ID")
def diff(a, b):
    """Compare file lists between two archived versions."""
    agent = ThemeDeploymentAgent()
    result = agent.diff_versions(a, b)
    click.echo(f"\n+ Added ({len(result['added'])})")
    for f in result["added"]:   click.echo(f"  + {f}")
    click.echo(f"\n- Removed ({len(result['removed'])})")
    for f in result["removed"]: click.echo(f"  - {f}")
    click.echo(f"\n= Common ({len(result['common'])}) files unchanged")


if __name__ == "__main__":
    cli()
