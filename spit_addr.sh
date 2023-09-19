#!/bin/bash

for((i=2;i<=254;i++)); {
    e=$(( i + 15 ));
    if [ $e -ge 254 ]; then
        echo "$i 254";
    else
        echo "$i  $e";
    fi;
    i=$e;
}