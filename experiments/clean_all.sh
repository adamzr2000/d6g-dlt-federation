#!/bin/bash

# Delete all CSV files in consumer/, provider/, and merged/ directories
find consumer/ provider/ merged/ -type f -name "*.csv" -exec rm -f {} \;

# Delete all TXT files in logs/ directory
find logs/ -type f -name "*.txt" -exec rm -f {} \;

echo "All CSV files in consumer/, provider/, and merged/ have been deleted."
echo "All TXT files in logs/ have been deleted."
