@echo off
echo Exporting leads from the Docker container...
docker cp export_leads.py phn-whatsapp-agent:/app/export_leads.py >nul 2>&1
docker exec phn-whatsapp-agent python export_leads.py
docker cp phn-whatsapp-agent:/app/interested_students.csv . >nul 2>&1
echo Done! Check the interested_students.csv file.
pause
