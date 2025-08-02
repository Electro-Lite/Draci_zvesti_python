function allowDrop(ev) {
            
    ev.preventDefault();
  }
  
  function drag(ev) {
    ev.dataTransfer.setData("text", ev.target.id);
  }
  
  function drop(ev) {
      if (ev.target.children.length > 0) {
          return;
      }
      if(ev.target.classList.contains('hand_card')){
          return
      }
      // Data to send in the POST request
      const data1 = { 
            name: 'John Doe', 
            email: 'john@example.com' 
        };

        // POST request using fetch
        fetch('/', {
            method: 'POST', // Use POST method
            headers: {
                'Content-Type': 'application/json' // Set the content type to JSON
            },
            body: JSON.stringify(data1) // Convert JavaScript object to JSON string
        })

      ev.preventDefault();
      var data = ev.dataTransfer.getData("text");
      ev.target.appendChild(document.getElementById(data));
      ev.target.children.length
      document.getElementById(data).draggable=false
    }