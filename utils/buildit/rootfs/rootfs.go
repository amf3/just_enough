// The rootfs package creates a directory structure that will become the basis of the
// root filesystem within the container.   The directory structure will follow the
// Linux Hierarchy Standard v3.0 https://refspecs.linuxfoundation.org/FHS_3.0/fhs/index.html
// but /bin and /lib are symbolically linked to /usr.
package rootfs

import (
	"io/ioutil"
	"log"

	"gopkg.in/yaml.v3"
)

type FSObjects struct {
	Path       string `yaml:"path"`
	Permission int    `yaml:"permission"`
	Category   string `yaml:"category"`
	LinkTo     string `yaml:"linkTo"`
	Source     string `yaml:"source"`
}

// I don't think this is right. Perhaps we should return the map to the caller.
var FsItems = make(map[string]FSObjects)

func loadFSConfig(configPath string) error {
	yamlData, err := ioutil.ReadFile("../configs/foo.yaml")
	if err != nil {
		log.Fatal(err)
	}
	err2 := yaml.Unmarshal(yamlData, &FsItems)
	if err2 != nil {
		log.Fatal(err2)
	}
}
