# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|

  config.vm.define "ci_33100" do |ci_33100|
    ci_33100.vm.box = "ubuntu/xenial64"
    ci_33100.vm.box_check_update = false
    ci_33100.vm.hostname = "ci-33100"
    ci_33100.vm.network "private_network", ip: "192.168.33.100"
    ci_33100.vm.provider "virtualbox" do |vb|
      vb.cpus = 2
      vb.memory = "512"
      vb.customize ["modifyvm", :id, "--cpuexecutioncap", "90"]
    end
  end

  config.vm.define "dev_front_33101" do |df_33101|
    df_33101.vm.box = "ubuntu/xenial64"
    df_33101.vm.box_check_update = false
    df_33101.vm.hostname = "df-33101"
    df_33101.vm.network "private_network", ip: "192.168.33.101"
    df_33101.vm.provider "virtualbox" do |vb|
      vb.cpus = 2
      vb.memory = "512"
      vb.customize ["modifyvm", :id, "--cpuexecutioncap", "90"]
    end
  end

  config.vm.define "dev_app_1_33102" do |da1_33102|
    da1_33102.vm.box = "ubuntu/xenial64"
    da1_33102.vm.box_check_update = false
    da1_33102.vm.hostname = "da1-33102"
    da1_33102.vm.network "private_network", ip: "192.168.33.102"
    da1_33102.vm.provider "virtualbox" do |vb|
      vb.cpus = 2
      vb.memory = "512"
      vb.customize ["modifyvm", :id, "--cpuexecutioncap", "90"]
    end
  end

  config.vm.define "dev_app_2_33103" do |da2_33103|
    da2_33103.vm.box = "ubuntu/xenial64"
    da2_33103.vm.box_check_update = false
    da2_33103.vm.hostname = "da2-33103"
    da2_33103.vm.network "private_network", ip: "192.168.33.103"
    da2_33103.vm.provider "virtualbox" do |vb|
      vb.cpus = 2
      vb.memory = "512"
      vb.customize ["modifyvm", :id, "--cpuexecutioncap", "90"]
    end
  end

  config.vm.define "dev_data_33104" do |dd_33104|
    dd_33104.vm.box = "ubuntu/xenial64"
    dd_33104.vm.box_check_update = false
    dd_33104.vm.hostname = "dd-33104"
    dd_33104.vm.network "private_network", ip: "192.168.33.104"
    dd_33104.vm.provider "virtualbox" do |vb|
      vb.cpus = 2
      vb.memory = "1024"
      vb.customize ["modifyvm", :id, "--cpuexecutioncap", "90"]
    end
  end

  config.vm.provision "shell" do |s|
    ssh_pub_key = File.readlines("#{Dir.home}/.ssh/id_rsa.pub").first.strip
    s.inline = <<-SHELL
      if [ ! -f ~/runonce ]
        then
          echo #{ssh_pub_key} >> /home/ubuntu/.ssh/authorized_keys
          touch ~/runonce
      fi
      ln -f -s /usr/bin/python3 /usr/bin/python
      apt-get update
      apt-get -y install htop vim
    SHELL
  end

end