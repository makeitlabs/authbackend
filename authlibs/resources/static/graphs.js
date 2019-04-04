
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
				legendbox = chart.querySelector("#bkglegend");
				for (var i=0;i<7;i++) {
								daylab = chart.querySelector("#label_day"+String(i+1));
								//console.log(daylab);
								//console.log(indata['weekdays']);
								daylab.innerHTML=indata['weekdays'][i];
				}
				legendy = 63;
				for (x in indata['legend']) {
					var u = indata['legend'][x];
					var svgns = "http://www.w3.org/2000/svg";
					itm = document.createElementNS(svgns, 'rect');
					itm.setAttributeNS(null,"style","opacity:1;fill:"+u['color']+";fill-opacity:1;stroke:none");
       		itm.setAttributeNS(null,"width",3);
       		itm.setAttributeNS(null,"height",3);
       		itm.setAttributeNS(null,"x",148.35);
       		itm.setAttributeNS(null,"y",legendy);
					legendy += 5;
					legendbox.appendChild(itm);

					text = document.createElementNS(svgns, 'text');
					text.setAttributeNS(null,"style","font-style:normal;font-weight:normal;font-size:2.95427346px;line-height:125%;font-family:sans-serif;text-align:start;letter-spacing:0px;word-spacing:0px;text-anchor:start;fill:#000000;fill-opacity:1;stroke:none;stroke-width:0.07385684px;stroke-linecap:butt;stroke-linejoin:miter;stroke-opacity:1");
       		text.setAttributeNS(null,"x",153.35);
       		text.setAttributeNS(null,"y",legendy-2.5);

					itm = document.createElementNS(svgns, 'tspan');
					itm.setAttributeNS(null,"style","text-align:start;text-anchor:start;stroke-width:0.07385684px");
       		itm.setAttributeNS(null,"x",153.35);
       		itm.setAttributeNS(null,"y",legendy-2.5);
       		itm.innerHTML = u['name']
					text.appendChild(itm);
					legendbox.appendChild(text);
				}
				for (x in indata['usage']) {
					var u = indata['usage'][x];
					// TODO BUG BKG Scale and offsets are totally off. Graph is inaccurate
					var xoffset=22.5
					var width=17.37;
					var xscale=2;
					var yscale=15.15; //??/
					var yoffset=56;
					var h= (u['endmin']-u['startmin'])/yscale;
					var x = xoffset+((Math.floor(u['startmin']/1440))*width);
					var y = ((u['startmin'] % 1440)/yscale)+yoffset;
					var color = u['color'];
					var svgns = "http://www.w3.org/2000/svg";
					itm = document.createElementNS(svgns, 'rect');
					itm.setAttributeNS(null,"style","opacity:1;fill:"+color+";fill-opacity:1;stroke:none");
       		itm.setAttributeNS(null,"width",width);
       		itm.setAttributeNS(null,"height",h);
       		itm.setAttributeNS(null,"x",x);
       		itm.setAttributeNS(null,"y",y);
					title = document.createElementNS(svgns, 'title');
					title.innerHTML=u['text'];
					itm.appendChild(title);
					box.appendChild(itm);
				}
		 })
			.fail(function(sender, message, details){
						 console.log("Sorry, something went wrong!",message,details);
		});
}
