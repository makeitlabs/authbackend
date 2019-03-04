
makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
   var json_data = JSON.stringify(data);
    return $.ajax({
        type: "GET",
        url: url,
        data: data,
        dataType: "json",
        contentType: "application/json;charset=utf-8"
    });
	
}

current_user_offset=0;
lastQuery="";

function DoSearchButton() {
	changedDropdownText();
	current_user_offset=0;
}


// and here a call example
function changedDropdownText(inputField,queryURL,outputList) {
	searchstr=document.getElementById(inputField).value;
	if (searchstr.length >= 3) 
		queryItem(searchstr,queryURL,outputList);
}



function queryItem(searchstr,queryURL,outputList) {
	lastQuery=searchstr;
	if (current_user_offset > 0) {
		q=queryURL+searchstr; 
		opt='offset='+String(current_user_offset);
	}
	else {
		q=queryURL+searchstr;
		opt=""
	}

/*

          <div class="form-group" style="padding:3px">
            <input type="checkbox"><label>Test</label>
          </div>

*/
	makePostCall(q, opt)
			.success(function(data){

						lst=document.getElementById(outputList);

						console.log(lst);
						var x = lst.getElementsByClassName("datarow")[0];
						while(x) {
							cb = x.getElementsByTagName("input")[0];
							var e=x;
							x = x.nextElementSibling;
							if ( cb.checked == false)
								e.parentNode.removeChild(e);
						}

						console.log(data);
						for (x in data){ 
							el = document.createElement("tr");
							t= `<div class="compact tightcbcell">
									<input name="input_member_`+data[x]['id']+`" type="checkbox"><label>`+data[x]['member']+`</label>
								</div>`;
							el.innerHTML=t;
							el.classList.add("datarow");
							el.classList.add("compact");
							lst.append(el);
						}
		
		
		 })
			.fail(function(sender, message, details){
						 console.log("Sorry, something went wrong!",message,details);
		});

}

function click_checkbox() {
	var x = document.querySelectorAll(".auth_user_cb")
	var memexist=false;
	for (i=0;i<x.length;i++) {
		if (x[i].checked) memexist=true;
	}

	var x = document.querySelectorAll(".auth_resource_cb")
	var resexist=false;
	for (i=0;i<x.length;i++) {
		if (x[i].checked) resexist=true;
	}
	btn = document.getElementById("authorize-button");
	if (memexist && resexist) {
		btn.removeAttribute("disabled");
		}
	else {
		btn.setAttribute("disabled",true);
		}
}



function authbutton() {
	var formdata = document.getElementById("formdata");
	var e  = formdata.querySelector("input");
	formdata.innerHTML="";
	/* TODO REMOVEME 
	while (e) {
		elm.removeChild(x);
		var e  = formdata.querySelector("input");
	};
	*/
	var el = document.createElement("input");
	el.innerHTML = "<input type=\"hidden\" name=\"authorize\""+
			"value=\"yes\" />";
	document.getElementById('formdata').appendChild(el);


	var xx = document.getElementById("modaltext");
	xx.innerHTML="Sure you want to authorize ";
	lst=document.getElementById("memberrows");

	var first=true;
	var num=0;
	for (i=0; i< lst.getElementsByClassName("memberrow").length;i++) {
		elm=lst.getElementsByClassName("memberrow")[i];
		td = elm.querySelectorAll("td");
		ch = td[0].childNodes[0];
		if (ch.checked) {
			if (!first)
				xx.innerHTML += ", "
			xx.innerHTML += td[2].innerHTML;
			xx.innerHTML += " "
			xx.innerHTML += td[3].innerHTML;
			first=false;

			var el = document.createElement("input");
			el.innerHTML = "<input type=\"hidden\" name=\"memberid_"+num+"\""+
				"value=\""+td[1].innerHTML+"\" />";
			document.getElementById('formdata').appendChild(el);
			num += 1;
		}
	}

	xx.innerHTML += " on "
	var first=true;
	var num=0;
	lst=document.getElementById("resourcerows");
	for (i=0; i< lst.getElementsByClassName("resourcerow").length;i++) {
		elm=lst.getElementsByClassName("resourcerow")[i];
		td = elm.querySelectorAll("td");
		ch = td[0].childNodes[0];
		if (ch.checked) {
			if (!first)
				xx.innerHTML += ", "
			xx.innerHTML += td[1].innerHTML;
			first=false;

			var el = document.createElement("input");
			el.innerHTML = "<input type=\"hidden\" name=\"resource_"+num+"\" "+
				"value=\""+td[1].innerHTML+"\" />";
			document.getElementById('formdata').appendChild(el);
			num += 1;

		}
	}

	xx.innerHTML += "?"
}

/* Init date picker */
$(document).ready(function () {
	$('#datepicker').datepicker({
			maxViewMode: 2,
			todayBtn: true,
			clearBtn: true,
			todayHighlight: true
	});
});
