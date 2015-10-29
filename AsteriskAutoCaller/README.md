Here is an Asterisk auto caller server. Originate server works with Asterisk through the AMI interface. 

1. Originate server has been designed only for unix systems. 
2. It has it's own tcp server interface which is uded for external connections.
3. TCP interface hast it's own string based protocol.
4. Server implements zombi proccess collector sort of internal garbage collector.
5. Multiproccess high performance engine which allows lots of simultaneous connections and call processing.
