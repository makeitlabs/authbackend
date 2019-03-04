
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

current_user_offset=0;
lastQuery="";

function DoSearchButton() {
	changedDropdownText();
	current_user_offset=0;
}

function DoAllButton() {
	queryMembers("*");
	document.getElementById("searchfield1").value="";
	current_user_offset=0;
}

// and here a call example
function changedDropdownText() {
	searchstr=document.getElementById("searchfield1").value;
	entermatch=document.getElementById("entermatchtext");
	membertable=document.getElementById("membertable");
	if (searchstr.length >= 3) {
		if (entermatch) entermatch.setAttribute("style","display:none");
		if (membertable) membertable.setAttribute("style","display:table");
	} else {
		if (entermatchtext) entermatch.setAttribute("style","display:block");
		//if (membertable) membertable.setAttribute("style","display:none");
		return;
	}
	queryMembers(searchstr);
}


function MoarUsers() {
	current_user_offset += 50;
	queryMembers(lastQuery);
}

function queryMembers(searchstr) {
	lastQuery=searchstr;
	opt = {};
	if (current_user_offset > 0) {
		q=MEMBER_SEARCH_URL+searchstr; 
		opt['offset']=String(current_user_offset);
	}
	else {
		q=MEMBER_SEARCH_URL+searchstr;
	}

	searchbox = document.getElementById("search_box");
	bb = searchbox.querySelectorAll(".member_filter_cb");
	for (b of bb) {
		if (b.checked)  {
			opt['filter_'+b.value]=1;
		}
	}

	makePostCall(q, opt)
			.success(function(data){

						lst=document.getElementById("memberrows");

						var x = lst.getElementsByClassName("memberrow")[0];

						/* Wipe list 
							If we are in "checkbox" mode - and boxes are checked - DON'T delte
							*/
						while(x) {
							cb = x.getElementsByTagName("input")[0];
							var e=x;
							x = x.nextElementSibling;
							if ((!cb) || ( cb.checked == false))
								e.parentNode.removeChild(e);
						}

						/* Add new data from query to list */
						/* TODO - in Checkbox mode - if there are checked people already in list - Don't re-add */
						for (x in data){ 
							el = document.createElement("tr");
							el.innerHTML = "<tr>"
							if (USE_MEMBER_CHECKBOXES)
								el.innerHTML += "<td><input type=\"checkbox\" onchange=\"click_checkbox();\" class=\"auth_user_cb\" /></td>";
							td=""
							/* DO not add URLs w/ member checkboxes. Kills codes that
							 pulls the member_id from this td */
							if (! USE_MEMBER_CHECKBOXES)
								if (MEMBER_URL) {
									td += "<a href=\""+MEMBER_URL+data[x]['member']+"\">";
								}
							td += data[x]['member'];
							if (! USE_MEMBER_CHECKBOXES)
								if (MEMBER_URL)
									td +="</a>";
							el.innerHTML += "<td>"+td+"</td>";
							el.innerHTML +=
								"<td>"+data[x]['firstname']+"</td>"+
								"<td>"+data[x]['lastname']+"</td>"+
								"<td>"+data[x]['email']+"</td>"+
								"<td>"+data[x]['active']+"</td>"+
								"<td>";
							el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['member']+"\">"+
							 "<img style=\"height:16px\" src=\""+STATIC_URL+"logicon.png\" />"+
							 "</a>";
							el.innerHTML += "&nbsp;<a href=\""+MEMBER_URL+data[x]['member']+"\">"+
							 "<img style=\"height:16px\" src=\""+STATIC_URL+"eye.png\" />"+
							 "</a>";
							el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['id']+"/access\">"+
							 "&nbsp;<img style=\"height:16px\" src=\""+STATIC_URL+"lock.png\" />"+
							 "</a>";
							el.innerHTML += "<a href=\""+MEMBER_URL+data[x]['id']+"/edit\">"+
							 "&nbsp;<img style=\"height:16px\" src=\""+STATIC_URL+"edit.png\" />"+
							 "</a>";
							el.innerHTML += "</td>"+
								"</tr>";
							el.classList.add("memberrow");
							lst.appendChild(el);
						}
						b = document.getElementById("moarUsers");
								if (data.length >= 50) {
							b.className = b.className.replace(/\binvisible\b/g, " visible ");
						} else {
							b.className = b.className.replace(/\bvisible\b/g, " invisible ");
						}
						//lstb.appennd(document.CreateNode("a",<a class="dropdown-item" href="#">Action</a>"
		
		
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
				"value=\""+td[1].innerHTML.trim()+"\" />";
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
