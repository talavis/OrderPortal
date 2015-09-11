/* OrderPortal
   Order documents indexed by keywords; title split up.
   Value: title.
*/
// Is hopefully evaluated only once...
var lint = {'and': 1,
	    'the': 1,
	    'was': 1,
	    'not': 1};
function(doc) {
    if (doc.orderportal_doctype !== 'order') return;
    var cleanup = doc.title.replace(/[:,']/g, " ");
    var words = cleanup.split(/\s+/);
    words.forEach(function(word) {
	if (word.length > 2 && !lint[word]) emit(word, doc.title);
    });
}