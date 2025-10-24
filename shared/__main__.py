"""
Shared module entrypoint
Provides command-line interface for shared utilities
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from .bootstrap_validator import (print_bootstrap_report,
                                  run_bootstrap_validation)
from .health_v2 import get_health_v2_summary, validate_health_v2
from .integration_contracts import (get_contract_status_summary,
                                    validate_integration_contracts)
from .path_registry import get_all_paths, get_repo_root
from .resource_monitor import get_resource_summary


def main():
    """Main entrypoint for shared module"""
    parser = argparse.ArgumentParser(description='Shared module utilities')
    parser.add_argument('command', choices=[
        'bootstrap', 'health', 'contracts', 'resources', 'paths', 'test'
    ], help='Command to run')
    
    args = parser.parse_args()
    
    if args.command == 'bootstrap':
        print("Running bootstrap validation...")
        validation = run_bootstrap_validation()
        print_bootstrap_report(validation)
        
    elif args.command == 'health':
        print("Running HealthV2 validation...")
        status = validate_health_v2()
        print(get_health_v2_summary(status))
        
        if not status.is_green:
            print("\nFailed probes:")
            for probe in status.probe_results:
                if not probe.status:
                    print(f"  ❌ {probe.probe_name}: {probe.message}")
        
    elif args.command == 'contracts':
        print("Running integration contracts validation...")
        contracts = validate_integration_contracts()
        print(get_contract_status_summary(contracts))
        
        if not contracts.all_contracts_pass:
            print("\nContract violations:")
            for violation in contracts.violations:
                if violation.severity == "error":
                    print(f"  ❌ {violation.contract_name}: {violation.message}")
        
    elif args.command == 'resources':
        print("Getting resource summary...")
        summary = get_resource_summary()
        print(f"Monitoring active: {summary['monitoring_active']}")
        print(f"Process count: {summary['process_count']}")
        print(f"Warning alerts: {summary['warning_alerts']}")
        print(f"Critical alerts: {summary['critical_alerts']}")
        
        if summary['processes']:
            print("\nProcesses:")
            for pid, proc in summary['processes'].items():
                print(f"  {proc['name']} (PID {pid}): {proc['rss_mb']:.1f}MB, {proc['cpu_percent']:.1f}% CPU")
        
        if summary['active_alerts']:
            print("\nActive alerts:")
            for alert in summary['active_alerts']:
                print(f"  {alert['severity'].upper()}: {alert['process_name']} {alert['alert_type']} "
                      f"{alert['current_value']:.1f} > {alert['threshold']:.1f}")
        
    elif args.command == 'paths':
        print("Getting all paths...")
        repo_root = get_repo_root()
        print(f"Repository root: {repo_root}")
        
        paths = get_all_paths()
        print("\nRegistered paths:")
        for key, path in paths.items():
            print(f"  {key}: {path}")
        
    elif args.command == 'test':
        print("Running E2E smoke tests...")
        try:
            from tests.test_e2e_smoke import run_smoke_tests
            success = run_smoke_tests()
            if success:
                print("\n✅ All smoke tests passed!")
                sys.exit(0)
            else:
                print("\n❌ Some smoke tests failed!")
                sys.exit(1)
        except ImportError as e:
            print(f"Failed to import smoke tests: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()