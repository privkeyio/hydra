"""Parallel execution commands for Hydra CLI."""

import asyncio
import os
import uuid
from pathlib import Path


def add_parallel_parser(subparsers):
    """Add parallel execution subcommands to ticket parser."""
    # Parallel execution command
    parallel_parser = subparsers.add_parser(
        "parallel", help="Execute tickets in parallel with dependency resolution"
    )
    parallel_parser.add_argument("tickets", help="Path to tickets.md file")
    parallel_parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=3,
        help="Number of parallel workers (default: 3)",
    )
    parallel_parser.add_argument(
        "--save-log", "-l", action="store_true", help="Save execution log to file"
    )
    parallel_parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip preflight validation checks"
    )
    parallel_parser.add_argument(
        "--async",
        action="store_true",
        dest="async_mode",
        help="Use async execution mode for better concurrency",
    )

    # Batch execution command
    batch_parser = subparsers.add_parser(
        "batch", help="Execute tickets in optimized batches to reduce session overhead"
    )
    batch_parser.add_argument("tickets", help="Path to tickets.md file")
    batch_parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=3,
        help="Number of concurrent batches (default: 3)",
    )
    batch_parser.add_argument(
        "--max-batch-size",
        "-b",
        type=int,
        default=5,
        help="Maximum tickets per batch (default: 5)",
    )
    batch_parser.add_argument(
        "--max-complexity",
        "-c",
        type=int,
        default=100,
        help="Maximum complexity score per batch (default: 100)",
    )
    batch_parser.add_argument(
        "--min-batch-tickets",
        "-m",
        type=int,
        default=2,
        help="Minimum tickets to form a batch (default: 2)",
    )
    batch_parser.add_argument(
        "--disable-batching",
        action="store_true",
        help="Disable ticket batching, execute individually",
    )
    batch_parser.add_argument(
        "--save-log", "-l", action="store_true", help="Save execution log to file"
    )
    batch_parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip preflight validation checks"
    )


def _handle_parallel_execution(args) -> int:
    """Handle parallel ticket execution with dependency resolution."""
    # Check if async mode is requested
    if getattr(args, "async_mode", False):
        return _handle_async_parallel_execution(args)
    else:
        return _handle_sync_parallel_execution(args)


def _handle_sync_parallel_execution(args) -> int:
    """Handle synchronous parallel ticket execution."""
    from hydra.dashboard import DashboardServer, DashboardState
    from hydra.parallel import ParallelExecutor
    from hydra.parallel.executor import ExecutionStatus
    from hydra.production_config import get_production_config

    try:
        # Load production configuration
        config = get_production_config()

        # Override with command line arguments if provided
        if hasattr(args, "workers"):
            config.max_parallel_tickets = args.workers

        # Apply environment variables from config
        for key, value in config.to_env_vars().items():
            os.environ[key] = value

        # Get absolute path to tickets file
        tickets_path = Path(args.tickets).resolve()
        if not tickets_path.exists():
            print(f"❌ Tickets file not found: {tickets_path}")
            return 1

        # Initialize dashboard if enabled
        dashboard_state = None
        dashboard_server = None
        if config.enable_dashboard:
            dashboard_state = DashboardState()
            dashboard_server = DashboardServer()
            dashboard_server.start(background=True)

        # Initialize executor with production config
        project_root = tickets_path.parent
        executor = ParallelExecutor(
            max_workers=config.max_parallel_tickets,
            project_root=str(project_root),
            dashboard_state=dashboard_state,
        )

        # Log configuration mode
        print(
            f"🔧 Production Mode: File locking {'enabled' if config.enable_file_locking else 'disabled'}"
        )
        print(
            f"🔧 Smart scheduling: {'enabled' if config.enable_smart_scheduling else 'disabled'}"
        )
        print(f"🎯 Loading tickets from: {tickets_path}")

        # Load tickets
        tickets = executor.load_tickets(str(tickets_path))
        if not tickets:
            print("❌ No pending tickets found")
            return 1

        # Run preflight validation unless skipped
        skip_preflight = getattr(args, "skip_preflight", False)
        if not skip_preflight:
            print("🚀 Running preflight validation...")
            from hydra.preflight import PreflightChecker

            checker = PreflightChecker()
            report = checker.run_preflight_checks(str(tickets_path))

            if report.has_critical_issues():
                print("🚨 PREFLIGHT FAILED - Critical issues found!")
                print("\nCritical Issues:")
                for check in report.get_critical_issues():
                    print(f"❌ {check.description}: {check.message}")
                print("\nUse --skip-preflight to override, but execution may fail.")
                return 1
            elif report.has_errors() or report.has_warnings():
                print("⚠️  Preflight validation completed with warnings/errors:")
                for check in report.get_failed_checks()[:3]:
                    print(f"{check.status_emoji} {check.description}: {check.message}")
                if len(report.get_failed_checks()) > 3:
                    print(
                        f"   ... and {len(report.get_failed_checks()) - 3} more issues"
                    )
                print("Proceeding with execution despite warnings...")
            else:
                print("✅ Preflight validation passed")
        else:
            print("⚡ Skipping preflight validation (--skip-preflight)")

        # Count only pending tickets
        pending_count = len(
            [t for t in tickets.values() if t.status == ExecutionStatus.PENDING]
        )
        total_count = len(tickets)
        completed_count = len(executor.completed_tickets)

        if completed_count > 0:
            print(f"✅ {completed_count} tickets already completed")
        print(f"📋 Found {pending_count} pending tickets")

        # Build execution plan
        plan = executor.build_execution_plan()

        # Initialize dashboard session if available
        if dashboard_state:
            session_id = str(uuid.uuid4())[:8]
            dashboard_state.start_session(
                session_id=session_id,
                tickets_path=str(tickets_path),
                total_tickets=len(tickets),
                total_waves=len(plan.waves),
                workers=args.workers,
            )

        # Execute plan
        summary = executor.execute_plan(plan, str(tickets_path))

        # Generate and print report
        report = executor.generate_report(summary)
        print(report)

        # Save log if requested
        if args.save_log:
            log_file = executor.save_execution_log(summary)
            print(f"\n📄 Execution log saved: {log_file}")

        # Return success if all tickets completed
        if summary["completed"] == summary["total_tickets"]:
            print("\n✅ All tickets completed successfully!")

            # Save completion report
            report_path = executor.save_completion_report(summary)
            print(f"\n📄 Completion report saved: {report_path}")

            if dashboard_server:
                print(
                    f"📊 Dashboard snapshot saved in: {tickets_path.parent}/.hydra/dashboard/"
                )
                print(
                    "\n💡 Tip: Keep the dashboard open at http://localhost:8080 to review results"
                )

            executor.shutdown()
            if dashboard_server:
                dashboard_server.stop()
            return 0
        else:
            functionally_completed = summary.get(
                "functionally_completed", summary["completed"]
            )
            quality_passed = summary.get("quality_passed", summary["completed"])
            total = summary["total_tickets"]

            if functionally_completed == total:
                print(f"\n✅ All {total} tickets executed successfully!")
                if quality_passed < functionally_completed:
                    print(
                        f"⚠️  {functionally_completed - quality_passed} tickets have quality issues"
                    )
                    print("   Review the output and fix quality issues as needed.")
            else:
                print(
                    f"\n⚠️ Execution incomplete: {functionally_completed}/{total} tickets executed"
                )
                if summary.get("failed", 0) > 0:
                    print(f"   ❌ {summary['failed']} tickets failed to execute")
                if summary.get("blocked", 0) > 0:
                    print(f"   ⛔ {summary['blocked']} tickets blocked by dependencies")

            # Still save a report even if incomplete
            if functionally_completed > 0:
                report_path = executor.save_completion_report(summary)
                print(f"\n📄 Completion report saved: {report_path}")

            executor.shutdown()
            if dashboard_server:
                dashboard_server.stop()
            return 1

    except Exception as e:
        print(f"❌ Parallel execution error: {e}")
        if "executor" in locals():
            executor.shutdown()
        if "dashboard_server" in locals() and dashboard_server:
            dashboard_server.stop()
        return 1


def _handle_async_parallel_execution(args) -> int:
    """Handle asynchronous parallel ticket execution."""
    from hydra.parallel.async_executor import AsyncExecutor
    from hydra.production_config import get_production_config

    async def async_main():
        try:
            # Load production configuration
            config = get_production_config()

            # Override with command line arguments
            if hasattr(args, "workers"):
                config.max_parallel_tickets = args.workers

            # Get absolute path to tickets file
            tickets_path = Path(args.tickets).resolve()
            if not tickets_path.exists():
                print(f"❌ Tickets file not found: {tickets_path}")
                return 1

            # Initialize async executor
            project_root = tickets_path.parent
            executor = AsyncExecutor(
                max_concurrent=config.max_parallel_tickets,
                project_root=str(project_root),
            )

            print(f"⚡ Async Parallel Mode: {config.max_parallel_tickets} workers")
            print(f"🎯 Loading tickets from: {tickets_path}")

            # Load tickets
            tickets = await executor.load_tickets(str(tickets_path))
            if not tickets:
                print("❌ No pending tickets found")
                return 1

            # Run preflight validation unless skipped
            skip_preflight = getattr(args, "skip_preflight", False)
            if not skip_preflight:
                print("🚀 Running preflight validation...")
                from hydra.preflight import PreflightChecker

                checker = PreflightChecker()
                report = checker.run_preflight_checks(str(tickets_path))

                if report.has_critical_issues():
                    print("🚨 PREFLIGHT FAILED - Critical issues found!")
                    return 1

            pending_count = len(
                [t for t in tickets.values() if t.status.name == "PENDING"]
            )
            print(f"📋 Found {pending_count} pending tickets")

            # Execute tickets asynchronously
            summary = await executor.execute_tickets_dynamically(str(tickets_path))

            # Generate and print report
            report = executor.generate_report(summary)
            print(report)

            # Save log if requested
            if args.save_log:
                log_file = await executor.save_execution_log(summary)
                print(f"\n📄 Execution log saved: {log_file}")

            # Return success if all tickets completed
            if summary["completed"] == summary["total_tickets"]:
                print("\n✅ All tickets completed successfully!")
                return 0
            else:
                return 1

        except Exception as e:
            print(f"❌ Async execution error: {e}")
            return 1

    try:
        # Run async processing
        return asyncio.run(async_main())
    except Exception as e:
        print(f"❌ Failed to start async execution: {e}")
        return 1


def _handle_batch_execution(args) -> int:
    """Handle batch ticket execution with reduced session overhead."""
    from hydra.dashboard import DashboardServer, DashboardState
    from hydra.parallel.batch_executor import BatchConfig, BatchExecutor
    from hydra.production_config import get_production_config

    async def batch_main():
        try:
            # Load production configuration
            config = get_production_config()

            # Override with command line arguments
            if hasattr(args, "workers"):
                config.max_parallel_tickets = args.workers

            # Apply environment variables from config
            for key, value in config.to_env_vars().items():
                os.environ[key] = value

            # Get absolute path to tickets file
            tickets_path = Path(args.tickets).resolve()
            if not tickets_path.exists():
                print(f"❌ Tickets file not found: {tickets_path}")
                return 1

            # Initialize dashboard if enabled
            dashboard_state = None
            dashboard_server = None
            if config.enable_dashboard:
                dashboard_state = DashboardState()
                dashboard_server = DashboardServer()
                dashboard_server.start(background=True)

            # Configure batch processing
            batch_config = BatchConfig(
                max_batch_size=getattr(args, "max_batch_size", 5),
                max_complexity_score=getattr(args, "max_complexity", 100),
                min_tickets_for_batch=getattr(args, "min_batch_tickets", 2),
                enable_batching=not getattr(args, "disable_batching", False),
            )

            # Initialize batch executor
            project_root = tickets_path.parent
            executor = BatchExecutor(
                batch_config=batch_config,
                max_concurrent=config.max_parallel_tickets,
                project_root=str(project_root),
                dashboard_state=dashboard_state,
            )

            print(
                f"📦 Batch Processing Mode: {'enabled' if batch_config.enable_batching else 'disabled'}"
            )
            print(f"🎯 Max batch size: {batch_config.max_batch_size}")
            print(f"🎯 Loading tickets from: {tickets_path}")

            # Load tickets and analyze for batching
            tickets = await executor.load_tickets(str(tickets_path))
            if not tickets:
                print("❌ No pending tickets found")
                return 1

            # Run preflight validation unless skipped
            skip_preflight = getattr(args, "skip_preflight", False)
            if not skip_preflight:
                print("🚀 Running preflight validation...")
                from hydra.preflight import PreflightChecker

                checker = PreflightChecker()
                report = checker.run_preflight_checks(str(tickets_path))

                if report.has_critical_issues():
                    print("🚨 PREFLIGHT FAILED - Critical issues found!")
                    print("\nCritical Issues:")
                    for check in report.get_critical_issues():
                        print(f"❌ {check.description}: {check.message}")
                    print("\nUse --skip-preflight to override, but execution may fail.")
                    return 1

            pending_count = len(
                [t for t in tickets.values() if t.status.name == "PENDING"]
            )
            completed_count = len(executor.completed_tickets)

            if completed_count > 0:
                print(f"✅ {completed_count} tickets already completed")
            print(f"📋 Found {pending_count} pending tickets")

            if batch_config.enable_batching and len(executor.batches) > 0:
                print(f"📦 Created {len(executor.batches)} batch groups:")
                for batch_id, batch in executor.batches.items():
                    print(
                        f"   {batch_id}: {len(batch.ticket_ids)} tickets ({batch.model})"
                    )

            # Execute with batch processing
            summary = await executor.execute_tickets_dynamically(str(tickets_path))

            # Generate and print report
            report = executor.generate_report(summary)
            print(report)

            # Save log if requested
            if args.save_log:
                log_file = await executor.save_execution_log(summary)
                print(f"\n📄 Execution log saved: {log_file}")

            # Return success if all tickets completed
            if summary["completed"] == summary["total_tickets"]:
                print("\n✅ All tickets completed successfully!")

                # Save completion report
                report_path = await executor.save_completion_report(summary)
                print(f"\n📄 Batch completion report saved: {report_path}")

                if summary.get("overhead_reduction", 0) > 0:
                    print(
                        f"⚡ Session overhead reduced by {summary['overhead_reduction']:.1f}%!"
                    )

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 0
            else:
                functionally_completed = summary.get(
                    "functionally_completed", summary["completed"]
                )
                quality_passed = summary.get("quality_passed", summary["completed"])
                total = summary["total_tickets"]

                if functionally_completed == total:
                    print(f"\n✅ All {total} tickets executed successfully!")
                    if quality_passed < functionally_completed:
                        print(
                            f"⚠️  {functionally_completed - quality_passed} tickets have quality issues"
                        )
                else:
                    print(
                        f"\n⚠️ Execution incomplete: {functionally_completed}/{total} tickets executed"
                    )

                executor.shutdown()
                if dashboard_server:
                    dashboard_server.stop()
                return 1

        except Exception as e:
            print(f"❌ Batch execution error: {e}")
            if "executor" in locals():
                executor.shutdown()
            if "dashboard_server" in locals() and dashboard_server:
                dashboard_server.stop()
            return 1

    try:
        # Run batch processing asynchronously
        return asyncio.run(batch_main())
    except Exception as e:
        print(f"❌ Failed to start batch execution: {e}")
        return 1


def handle_parallel_commands(args) -> int:
    """Handle parallel execution commands."""
    action = getattr(args, "ticket_action", None)

    if action == "parallel":
        return _handle_parallel_execution(args)
    elif action == "batch":
        return _handle_batch_execution(args)
    else:
        # Default to parallel if no specific action
        return _handle_parallel_execution(args)
