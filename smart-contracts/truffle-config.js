module.exports = {
  networks: {
    development: {
      host: "192.168.56.104", 
      port: 7545,
      network_id: "*"
    },

    dlt_network: {
      host: process.env.NODE_IP,
      port: process.env.WS_PORT,            
      network_id: "2024",    
      websockets: true       
    },
  },
  compilers: {
    solc: {
      version: "0.5.0",   
    }
  },
};
