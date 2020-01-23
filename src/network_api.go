package main

import (
	"fmt"
	"log"
	"os/exec"
	"strings"
	"regexp"
)

var notnics = []string{"lo", "fwe", "fwip", "tap", "plip", "pfsync", "pflog",
	"tun", "sl", "faith", "ppp", "brige", "ixautomation", "vm-ixautomation"}

func networklist() []string {
	cmdOutput, err := exec.Command("ifconfig", "-l").Output()
	if err != nil {
		log.Fatal(err)
	}
	network_card := strings.Split(string(cmdOutput), " ")
	devicelist := []string{}
	for device := range network_card {
		reg, err := regexp.Compile("[^a-z]+")
		if err != nil {
			log.Fatal(err)
		}
		card := reg.ReplaceAllString(network_card[device], "")
		notnisc_string := strings.Join(notnics, " ")
		if !strings.Contains(notnisc_string, card) {
			devicelist = append(devicelist, network_card[device])
		}
	}
	return devicelist
}

func main() {
	fmt.Println(networklist()[0])
}
