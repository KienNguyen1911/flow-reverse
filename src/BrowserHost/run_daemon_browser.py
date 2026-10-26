"""Keep CloakBrowser running in foreground/daemon mode on winsta0\\default for CDP automation."""
import sys
import time

from src.BrowserHost.launch_profile import (
    VAULT_DIR,
    build_child_env,
    build_command,
    load_or_create_profile,
    resolve_binary,
    spawn_browser_process,
    validate_and_repair,
    wait_for_cdp,
)
from src.BrowserHost.pool_supervisor import PoolSupervisor


def main():
    profile = "aaaaa"
    port = 4023
    cfg, _, cfg_path = load_or_create_profile(profile, VAULT_DIR)
    validate_and_repair(cfg, cfg_path, profile)
    user_data_dir = cfg_path.parent / "user_data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    binary = resolve_binary()
    cmd = build_command(
        cfg,
        binary,
        user_data_dir,
        port,
        url="https://flow.google.com/project/006f6e93-2d22-4a3d-9b03-1a902a50fd10",
    )
    env = build_child_env()
    print(f"[daemon] Spawning CloakBrowser on winsta0\\default (port {port}, profile {profile})...")
    sys.stdout.flush()
    pid = spawn_browser_process(cmd, env=env)
    print(f"[daemon] Started PID={pid}, waiting for CDP...")
    sys.stdout.flush()
    wait_for_cdp(port, 30.0)
    try:
        while PoolSupervisor.is_process_running(pid):
            time.sleep(2.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
