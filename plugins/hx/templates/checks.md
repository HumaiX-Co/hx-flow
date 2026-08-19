<!-- hx-flow checks template · BUDGET: 25 lines
     THIS IS THE KEY TO LANGUAGE INDEPENDENCE: the plugin carries no stack knowledge, this file does.
     Produced by /hx:map (detection ladder: task runner -> CI files -> manifest -> ask the human).
     Capability names are UNIVERSAL, commands are LOCAL.
     Capabilities: lint format typecheck test-unit test-integration test-all e2e build migration run-dev extra doctor
     Placeholders: {pattern} {msg} {file}
     Anything marked cost:high runs ONCE before ship, never per slice. -->

platform: <windows-dev|linux-dev> / <linux-ci>
runner: <detected task runner|none>
verified: <YYYY-MM-DD>   # were the commands actually executed and confirmed to work
shell: <auto|bash|platform>   # declared commands below use POSIX syntax, so bash is usual.
                              # 'platform' runs cmd.exe on Windows and WILL break /dev/null etc.

scope <path/>
  doctor:      <cheap readiness probe: are this scope's dependencies installed?>
  lint:        <command>
  typecheck:   <command>
  test-unit:   <command {pattern}>
  test-all:    <command>
  migration:   <command {msg}>
  build:       <command>

scope <path/>
  lint:        <command>
  test-unit:   <command {pattern}>
  e2e:         <command>            # cost: high
  extra:       <command>            # cost: high

security
<!-- hx-security is a POLICY ENGINE, not a scanner. Scan commands live here.
     audit-block is REQUIRED: if undefined, ship is blocked (missing config is not "safe").
     audit-block contract: exit NON-ZERO when a blocking (critical/high) vulnerability exists.
     audit-count contract: print the TOTAL vulnerability COUNT (for the ratchet, optional). -->
  audit-block: <command>
  audit-count: <command>
  secret-scan: <command>
  sast:        <command>

<!-- A declared command is not a working command. POSIX-only scripts break on Windows;
     /hx:map runs each one once and records a local equivalent when it fails. -->
