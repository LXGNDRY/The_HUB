"""
GCP Bot — CLI Entry Point

Theme Deployment Agent:
  python cli.py deploy --dir ./my-theme --label summer-drop-v2
  python cli.py versions
  python cli.py rollback --version 20240517T120000Z
  python cli.py download --dest ./downloaded-theme
  python cli.py push-shopify --dir ./my-theme --theme-id 123456789
  python cli.py diff --a 20240517T120000Z --b 20240518T090000Z

Compute Agent:
  python cli.py list-vms --zone us-central1-a
  python cli.py list-all-vms
  python cli.py start-vm --zone us-central1-a --name my-vm
  python cli.py stop-vm  --zone us-central1-a --name my-vm
  python cli.py restart-vm --zone us-central1-a --name my-vm
  python cli.py delete-vm  --zone us-central1-a --name my-vm --confirm
  python cli.py create-vm  --zone us-central1-a --name my-vm --machine e2-micro
  python cli.py list-snapshots
  python cli.py cleanup-snapshots --days 30
  python cli.py auto-stop-idle --zone us-central1-a --cpu 5.0

Billing Agent:
  python cli.py billing-info
  python cli.py budgets
  python cli.py budget-check
  python cli.py spend --dataset billing_export --table gcp_billing_export_v1_XXXX --days 30
  python cli.py spikes --dataset billing_export --table gcp_billing_export_v1_XXXX
  python cli.py billing-check --dataset billing_export --table gcp_billing_export_v1_XXXX
"""

import click
from agents.theme_deployment_agent import ThemeDeploymentAgent
from agents.compute_agent import ComputeAgent
from agents.billing_agent import BillingAgent


@click.group()
def cli():
    """GCP Bot — Legendary Branding Infrastructure CLI"""
    pass


# ═══════════════════════════════════════════════════════════
# THEME DEPLOYMENT AGENT
# ═══════════════════════════════════════════════════════════

@cli.command()
@click.option("--dir",   required=True, help="Local path to theme directory")
@click.option("--label", default=None,  help="Human-readable version label")
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
@click.option("--version", required=True, help="Version ID to roll back to")
def rollback(version):
    """Roll back the live GCS snapshot to a previous version."""
    ThemeDeploymentAgent().rollback(version)


@cli.command()
@click.option("--dest", required=True, help="Local directory to download live theme into")
def download(dest):
    """Download the current live theme snapshot from GCS."""
    ThemeDeploymentAgent().download_live(dest)


@cli.command("push-shopify")
@click.option("--dir",      required=True, help="Local theme directory")
@click.option("--theme-id", required=True, help="Shopify theme ID")
def push_shopify(dir, theme_id):
    """Push local theme files directly to Shopify via Admin API."""
    ThemeDeploymentAgent().push_to_shopify(dir, theme_id)


@cli.command()
@click.option("--a", required=True, help="First version ID")
@click.option("--b", required=True, help="Second version ID")
def diff(a, b):
    """Compare file lists between two archived versions."""
    result = ThemeDeploymentAgent().diff_versions(a, b)
    click.echo(f"\n+ Added ({len(result['added'])})")
    for f in result["added"]:   click.echo(f"  + {f}")
    click.echo(f"\n- Removed ({len(result['removed'])})")
    for f in result["removed"]: click.echo(f"  - {f}")
    click.echo(f"\n= Common ({len(result['common'])}) files unchanged")


# ═══════════════════════════════════════════════════════════
# COMPUTE AGENT
# ═══════════════════════════════════════════════════════════

@cli.command("list-vms")
@click.option("--zone", required=True, help="GCP zone e.g. us-central1-a")
def list_vms(zone):
    """List all VM instances in a zone."""
    ComputeAgent().list_instances(zone)


@cli.command("list-all-vms")
def list_all_vms():
    """List VM instances across all zones."""
    ComputeAgent().list_all_instances()


@cli.command("start-vm")
@click.option("--zone", required=True)
@click.option("--name", required=True)
def start_vm(zone, name):
    """Start a stopped VM instance."""
    ComputeAgent().start_instance(zone, name)


@cli.command("stop-vm")
@click.option("--zone", required=True)
@click.option("--name", required=True)
@click.option("--dry-run", is_flag=True, default=False)
def stop_vm(zone, name, dry_run):
    """Stop a running VM instance."""
    ComputeAgent(dry_run=dry_run).stop_instance(zone, name)


@cli.command("restart-vm")
@click.option("--zone", required=True)
@click.option("--name", required=True)
def restart_vm(zone, name):
    """Hard restart a VM instance."""
    ComputeAgent().restart_instance(zone, name)


@cli.command("delete-vm")
@click.option("--zone",    required=True)
@click.option("--name",    required=True)
@click.option("--confirm", is_flag=True, default=False, help="Must pass --confirm to actually delete")
def delete_vm(zone, name, confirm):
    """Permanently delete a VM. Requires --confirm flag."""
    if not confirm:
        click.echo("⚠️  Pass --confirm to actually delete the VM. No changes made.")
        return
    ComputeAgent().delete_instance(zone, name)


@cli.command("create-vm")
@click.option("--zone",    required=True)
@click.option("--name",    required=True)
@click.option("--machine", default="e2-micro", help="Machine type (default: e2-micro)")
@click.option("--disk",    default=20,         help="Boot disk size GB (default: 20)")
def create_vm(zone, name, machine, disk):
    """Create a new VM instance."""
    ComputeAgent().create_instance(zone, name, machine_type=machine, disk_size_gb=disk)


@cli.command("list-snapshots")
def list_snapshots():
    """List all disk snapshots in the project."""
    ComputeAgent().list_snapshots()


@cli.command("cleanup-snapshots")
@click.option("--days",    default=30,    help="Delete snapshots older than N days")
@click.option("--dry-run", is_flag=True,  default=False)
def cleanup_snapshots(days, dry_run):
    """Delete snapshots older than N days."""
    ComputeAgent(dry_run=dry_run).delete_snapshots_older_than(days)


@cli.command("auto-stop-idle")
@click.option("--zone",    required=True)
@click.option("--cpu",     default=5.0, help="CPU % threshold (default: 5.0)")
@click.option("--dry-run", is_flag=True, default=False)
def auto_stop_idle(zone, cpu, dry_run):
    """Auto-stop VMs with average CPU below threshold."""
    stopped = ComputeAgent(dry_run=dry_run).auto_stop_idle(zone, cpu_threshold=cpu)
    click.echo(f"\nStopped {len(stopped)} idle VM(s): {stopped}")


# ═══════════════════════════════════════════════════════════
# BILLING AGENT
# ═══════════════════════════════════════════════════════════

@cli.command("billing-info")
def billing_info():
    """Show billing account info for the project."""
    BillingAgent().get_project_billing_info()


@cli.command("budgets")
def budgets():
    """List all budgets on the billing account."""
    BillingAgent().get_budgets()


@cli.command("budget-check")
def budget_check():
    """Check budget status against BUDGET_THRESHOLD."""
    BillingAgent().check_budget_status()


@cli.command("spend")
@click.option("--dataset", required=True, help="BigQuery dataset name")
@click.option("--table",   required=True, help="BigQuery billing export table name")
@click.option("--days",    default=30,    help="Number of past days (default: 30)")
@click.option("--export",  default=None,  help="Optional CSV output path")
def spend(dataset, table, days, export):
    """Get spend report by service from BigQuery Billing Export."""
    agent = BillingAgent()
    data  = agent.get_spend_report_from_bq(dataset, table, days=days)
    if export:
        agent.export_report(data, export, fmt="csv")


@cli.command("spikes")
@click.option("--dataset",  required=True)
@click.option("--table",    required=True)
@click.option("--pct",      default=None, type=float, help="Override spike threshold %")
def spikes(dataset, table, pct):
    """Detect day-over-day cost spikes from BigQuery Billing Export."""
    BillingAgent().detect_spend_spikes(dataset, table, spike_pct=pct)


@cli.command("billing-check")
@click.option("--dataset", default=None)
@click.option("--table",   default=None)
def billing_check(dataset, table):
    """Run full daily billing health check."""
    BillingAgent().run_daily_check(bq_dataset=dataset, bq_table=table)


if __name__ == "__main__":
    cli()
