#!/bin/bash
echo Creating archive `echo $(pwd) | awk -F'/' '{print $NF}'`_`date +'%d-%m-%Y'`.zip
7z a `echo $(pwd) | awk -F'/' '{print $NF}'`_`date +'%d-%m-%Y'`.zip * -x!images/*
