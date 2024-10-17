module.exports = {
  networks: {
    development: {
      host: "192.168.56.104", 
      port: 7545,
      network_id: "*"
    },

    node1: {
      host: process.env.IP_NODE_1,
      port: process.env.WS_PORT_NODE_1,            
      network_id: "1234",    
      websockets: true       
    },

    node2: {
      host: "192.168.56.105",
      port: 3335,            
      network_id: "1234",    
      websockets: true       
    },

  },
  compilers: {
    solc: {
      version: "0.5.0",   
    }
  },
};
