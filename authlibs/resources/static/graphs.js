
makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
   var json_data = JSON.stringify(data);
	// console.log("QERY "+url);
	//console.log(json_data);
    return $.ajax({
        type: "GET",
        url: url,
        data: data,
        dataType: "json",
        contentType: "application/json;charset=utf-8"
    });
	
}


function queryResources(url) {
	makePostCall(url, null)
			.success(function(indata){
				var data = google.visualization.arrayToDataTable(indata['data']);
				var chart;
				if (indata['type']=='pie')
								chart = new google.visualization.PieChart(document.getElementById('chart_div'));
				else
								chart = new google.visualization.AreaChart(document.getElementById('chart_div'));
				
        chart.draw(data, indata['opts']);
		 })
			.fail(function(sender, message, details){
						 console.log("Sorry, something went wrong!",message,details);
		});
}

function graphButton(button,url) {
	queryResources(url);
}

function calendarButton(button,url) {
	makePostCall(url, null)
			.success(function(indata){
				chart = document.getElementById('chart_div');
				chart.innerHTML = indata['data'];
				box = chart.querySelector("#bkgdraw");
				console.log(box);
				for (var i=0;i<7;i++) {
								daylab = chart.querySelector("#label_day"+String(i+1));
								console.log(daylab);
								console.log(indata['weekdays']);
								daylab.innerHTML=indata['weekdays'][i];
				}
				for (x in indata['usage']) {
					var u = indata['usage'][x];
					console.log(u);
					// TODO BUG BKG Scale and offsets are totally off. Graph is inaccurate
					var xoffset=22.5
					var width=17.37;
					var xscale=2;
					var yscale=15.5; //??/
					var yoffset=56;
					var h= (u['endmin']-u['startmin'])/yscale;
					var x = xoffset+((Math.floor(u['startmin']/1440))*width);
					var y = ((u['startmin'] % 1440)/yscale)+yoffset;
					itm = `
    <rect
       style="opacity:1;fill:#ff0000;fill-opacity:1;stroke:none"
       width="40"
       height="`+String(h)+`"
       x="`+String(x)+`"
       y="`+String(y)+`"
					`;

					var svgns = "http://www.w3.org/2000/svg";
					itm = document.createElementNS(svgns, 'rect');
					itm.setAttributeNS(null,"style","opacity:1;fill:#ff0000;fill-opacity:1;stroke:none");
       		itm.setAttributeNS(null,"width",width);
       		itm.setAttributeNS(null,"height",h);
       		itm.setAttributeNS(null,"x",x);
       		itm.setAttributeNS(null,"y",y);
					box.appendChild(itm);
				}
		 })
			.fail(function(sender, message, details){
						 console.log("Sorry, something went wrong!",message,details);
		});
}
