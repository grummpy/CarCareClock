# Writes a Task Scheduler XML file. Does not register it.
# Registration is a separate opt-in on the carcareclock install-checker command.
Set-Location (Join-Path $PSScriptRoot "..")
python -m carcareclock install-checker task @args
